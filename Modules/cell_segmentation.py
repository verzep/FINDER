"""implementation of CellSegmentation"""

import os
import json
import numpy as np
import h5py
import matplotlib.pyplot as plt
import pandas as pd
from skimage import measure
from skimage import filters
from skimage.filters import threshold_otsu


def get_index(x, y, xc):
    """transforms 2D coordinate xc into 1D index for given x-y-grid """

    n_x, n_y = x.shape[1], x.shape[0]
    dx, dy = x[1, 1]-x[0, 0], y[1, 1]-y[0, 0]
    x_min, y_min = x[0, 0], y[0, 0]

    x_index = (np.round((xc[:, 0]-x_min)/dx)).astype(int)
    y_index = (np.round((xc[:, 1]-y_min)/dy)).astype(int)

    x_index = np.minimum(n_x-1, np.maximum(0, x_index))
    y_index = np.minimum(n_y-1, np.maximum(0, y_index))

    return y_index*n_x+x_index

def load_points(filename):
    """Loads x-y-coordinates from .txt or .hdf5-file"""
    #Check if file exists
    assert os.path.isfile(filename), f"File {filename} not found"

    if filename[-3:] == 'txt':
        xc = np.loadtxt(filename)
    elif filename[-4:] == 'hdf5':
        f = h5py.File(filename, 'r')
        dset = f['locs']
        xc = np.stack((dset["x"], dset["y"])).T
    print(str(len(xc)) + ' points loaded from '+filename)
    return xc

def select_outcell(labels, pad_cell_border):
    """selects zero labels as outcell, and pads with pad_cell_border number of pixels"""

    h = (labels > 0)
    for _ in range(pad_cell_border):
        h[1:-1, 1:-1] = (h[1:-1, 1:-1]) | (h[:-2, 1:-1]) |\
                            (h[2:, 1:-1]) | (h[1:-1, :-2]) | (h[1:-1, 2:])
    im_outcell = np.bitwise_not(h)

    return im_outcell

def get_masked_localization(x, y, xc, im_mask):
    """selects localizations from a masked grid"""

    h_incell_flat = (im_mask.T).flatten()
    mask = h_incell_flat[get_index(x, y, xc)]
    xc_selected = xc[mask, :]

    return xc_selected

def select_incell(labels, h):
    """selects most occurring label as incell"""

    df_lab = pd.DataFrame()
    df_lab['labels'] = (labels[labels > 0]).flatten()
    df_lab['index1'] = df_lab.index

    label_incell = (df_lab.groupby(by='labels').count().idxmax())['index1']

    im_incell = np.zeros_like(h, dtype=np.bool_)
    im_incell[labels == label_incell] = True

    return im_incell


class CellSegmentation:
    """splits localizations into inside and outside cell and clusters subset"""

    def __init__(self, basefolder):

        self.basefolder = basefolder
        self.parameters = self.load_parameters()
        self.output_mode = 2
        #OUTPUT_MODE 0 = no output other than results
        #OUTPUT_MODE 1 = basic output (txt files for images)
        #OUTPUT_MODE 2 = plot output (plots,graphs etc)

        if not os.path.exists(self.__get_inout_folder()):
            print("creating the output folder...")
            os.makedirs(self.__get_inout_folder())
            print("output folder created in " + basefolder)

    def __get_inout_folder(self, inout="Output", filename=None):
        """return name of output folder"""
        if filename==None:
            return os.path.join(self.basefolder,inout)
        else:
            return os.path.join(self.basefolder, inout, filename)

    def load_parameters(self):
        """loads parameters from file or sets default parmeters"""

        parameterfile = self.__get_inout_folder(inout="Input", filename='PARAMETERS_splitInOutCell.json')
        if os.path.isfile(parameterfile):
            with open(parameterfile) as json_file:
                parameters = json.load(json_file)
        else:
            print("parameterfile not found. Using default parameters.")
            parameters = {"quantile_of_nonzero":True,\
                          "intensity_quantile_cutoff":0.9,\
                          "sigma_gaussian_filter":10,\
                          "N_x":1000,\
                          "pad_cell_border":20}# in pixels (see N_x for pixel number in x-direction)
        return parameters

    def save_parameters(self):
        """saves parameters to file"""
        with open(self.__get_inout_folder(filename='PARAMETERS_splitInOutCell.json'), 'w') as json_file:
            json.dump(self.parameters, json_file, indent=4)


    def get_image_from_localizations(self, xc, n_x, name):
        """plots and returns 2D histogram of localizations"""

        xc_min = np.min(xc, axis=0)
        xc_max = np.max(xc, axis=0)

        #have N points in the x-dimension
        n_y = int(n_x*(xc_max[1]-xc_min[1])/(xc_max[0]-xc_min[0]))

        print("heat map with dimensions "+str(n_x)+" x "+str(n_y))

        xedges = np.linspace(xc_min[0], xc_max[0], n_x+1)
        yedges = np.linspace(xc_min[1], xc_max[1], n_y+1)

        h, xedges, yedges = np.histogram2d(xc[:, 0], xc[:, 1], bins=(xedges, yedges))

        x, y = np.meshgrid((xedges[1:] + xedges[:-1]) / 2, (yedges[1:] + yedges[:-1]) / 2)

        if self.output_mode >= 1:
            np.savetxt(self.__get_inout_folder(filename=name+"_H.txt"), h, fmt="%f")

        if self.output_mode >= 2:
            _, ax = plt.subplots(1, 1, figsize=(5, 5))
            ax.imshow(h, cmap='gray', vmax=5)
            ax.axis('off')
            plt.savefig(self.__get_inout_folder(filename=name+'_image.pdf'))

        return h, x, y

    def segmentation(self):
        """splits localizations into low- and high-density region (out vs incell)"""

        outputfolder = self.__get_inout_folder()
        parameters = self.parameters

        # if(os.path.isfile(outputfolder+'X_incell.txt') and \
        #     os.path.isfile(outputfolder+'X_outcell.txt')):
        #     xc_incell = self.load_points(outputfolder+'X_incell.txt')
        #     xc_outcell = self.load_points(outputfolder+'X_outcell.txt')
        #else:
        xc = load_points(self.__get_inout_folder('Input','XC.hdf5'))

        # Step 1: Produce image
        h, x, y = self.get_image_from_localizations(xc, parameters['N_x'], 'heatmap_XC')

        # Step 2 a: Thresholding: Avoid long tail, set threshold at quantile of nonzero pixels
        if parameters['quantile_of_nonzero']:
            cutoff_h = np.quantile(h[h > 0], parameters['intensity_quantile_cutoff'])
        else:
            cutoff_h = np.quantile(h, parameters['intensity_quantile_cutoff'])
        h[h > cutoff_h] = cutoff_h

        # Step 2 b: Gaussian Filtering
        g_img = filters.gaussian(h, sigma=parameters['sigma_gaussian_filter'])

        # Step 2 c: Otsu's Thresholding
        binary = (g_img > threshold_otsu(g_img))

        # Step 2 d: Segmentation
        labels = measure.label(binary)

        #Step 2 e: Select in and out cell
        im_incell = select_incell(labels, h)
        im_outcell = select_outcell(labels, parameters['pad_cell_border'])

        # Step 3: Save GetImageFromLocalizations
        xc_incell = get_masked_localization(x, y, xc, im_incell)
        xc_outcell = get_masked_localization(x, y, xc, im_outcell)

        np.savetxt(outputfolder+"X_incell.txt", xc_incell, fmt="%f")
        np.savetxt(outputfolder+"X_outcell.txt", xc_outcell, fmt="%f")

        self.save_parameters()

        if self.output_mode >= 1:
            self.get_image_from_localizations(xc_incell, parameters['N_x'], 'heatmap_XCincell')
            self.get_image_from_localizations(xc_outcell, parameters['N_x'], 'heatmap_XCoutcell')

        print("segmentation completed successfully")

        return xc_incell, xc_outcell
