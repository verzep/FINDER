import numpy as np
from sklearn.cluster import DBSCAN

class DbscanLoop:

    def __init__(self, eps,min_samples):
        self.eps         = eps
        self.min_samples = min_samples
      
    def fit(self,XS):
                
        XS_full  = XS;
        n_old    = len(XS);
        idx_core = np.arange(len(XS));
        DB = DBSCAN(eps=self.eps,min_samples=self.min_samples).fit(XS);            
        XS = XS[DB.core_sample_indices_]     
        
        while((n_old != len(XS)) and (len(XS)>0)):
            n_old    = len(XS)
            idx_core = idx_core[DB.core_sample_indices_]
            DB       = DBSCAN(eps=self.eps,min_samples=self.min_samples).fit(XS);     
            XS       = XS[DB.core_sample_indices_];  
            
        labels_ = -1*np.ones((len(XS_full),),dtype=int);
        labels_[idx_core] =  DB.labels_;
        
        self.labels_ = labels_;
        return self;