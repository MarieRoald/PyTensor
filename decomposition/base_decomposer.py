"""
Contains the base class for all decomposition methods in PyTensor
"""


from abc import ABC, abstractmethod, abstractproperty
import numpy as np


__author__ = "Marie Roald & Yngve Mardal Moe"


class BaseDecomposer(ABC):
    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def init_components(self, initial_decomposition=None):
        pass

    @abstractproperty
    def reconstructed_X(self):
        pass
    
    def set_target(self, X):
        self.X = X
        self.X_norm = np.linalg.norm(X)

    @property
    def explained_variance(self):
        # TODO: Cache result
        return 1 - self.SSE/np.linalg.norm(self.X)**2

    @property
    def SSE(self):
        # TODO: Cache result
        return np.linalg.norm(self.X - self.reconstructed_X)**2
    
    @property
    def MSE(self):
        # TODO: Cache result
        return self.SSE/np.prod(self.X.shape)
    
    @property
    def RMSE(self):
        # TODO: Cache result
        return np.sqrt(self.MSE)

    @abstractmethod
    def loss(self):
        pass
   
    @abstractmethod
    def _fit(self):
        pass

    def _init_fit(self, X, max_its=None, initial_decomposition=None):
        self.init_components(initial_decomposition=initial_decomposition)
        self.set_target(X)
        if max_its is not None:
            self.max_its = max_its

    def fit(self, X, y=None, *, max_its=None, initial_decomposition=None):
        """Fit a CP model. Precomputed components must be specified if init method is `precomputed`.

        Arguments:
        ----------
        X : np.ndarray
            The tensor to fit
        y : None
            Ignored, included to follow sklearn standards.
        max_its : int (optional)
            If set, then this will override the class's max_its.
        initial_decomposition : tuple
            A tuple parametrising a Kruskal tensor.
            The first element is a list of factor matrices and the second element is an array containing the weights.
        """
        self._init_fit(X=X, max_its=max_its, initial_decomposition=initial_decomposition)
        self._fit()
    
    def continue_fit(self, max_its=None):
        if max_its is not None:
            self.max_its = max_its
        self._fit()