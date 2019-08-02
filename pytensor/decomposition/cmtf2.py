import h5py
import numpy as np
import itertools
from .cp import CP_ALS

from . import decompositions
from ..base import unfold
from .. import base

class CMTF_ALS(CP_ALS):
    DecompositionType = decompositions.CoupledTensors
    @property
    def SSE(self):
        """Computes the sum squared error of the decomposition
        
        Returns
        -------
        float
            Sum of squared error.
        """
        # TODO: Cache result
        return np.linalg.norm(self.X - self.reconstructed_X)**2 + self.coupled_matrices_SSE

    @property
    def MSE(self):
        """Computes the mean squared error of the decomposition.
        
        Returns
        -------
        float
            Mean of squared error.
        """
        #raise NotImplementedError('Not implemented') 
        # TODO: fix this
        num_elements = np.prod(self.X.shape) + sum(np.prod(Yi.shape) for Yi in self.coupled_matrices)
        return self.SSE/num_elements

    @property
    def coupled_matrices_SSE(self):
        """Computes total SSE for all coupled matrices.
        
        Returns
        -------
        float
            SSE for couple matrices.
        """
        SSE = 0

        for Y, reconstructed_Y in zip(self.coupled_matrices, self.reconstructed_coupled_matrices):
            SSE += np.linalg.norm(Y - reconstructed_Y)**2
        return SSE

    @property
    def RMSE(self):
        """        
        Returns RMSE of the decomposition
        """
        return np.sqrt(self.MSE)

    @property
    def reconstructed_coupled_matrices(self):
        """        
        Returns
        -------
        list(np.ndarray)
            The coupled matrices.
        """
        return self.decomposition.construct_matrices()

    @property
    def coupled_factor_matrices(self):
        """[summary]
        
        Returns
        -------
        list(np.ndarray)
            The coupled factor matrices.
        """
        return self.decomposition.coupled_factor_matrices

    @property
    def uncoupled_factor_matrices(self):
        """        
        Returns
        -------
        list(np.ndarray)
            The uncoupled factor matrices.
        """
        return self.decomposition.uncoupled_factor_matrices
    
    @property
    def coupling_modes(self):
        """        
        Returns
        -------
        list(int)
            The modes the matrices are coupled to the tensor along.
        """
        return self.decomposition.coupling_modes

    def fit_transform(self, X, coupled_matrices, coupling_modes, y=None, max_its=None, tensor_missing_values=None, impute_matrix_axis=None, penalty=None):
        """Executes coupled-tensor-matrix factorisation and returns the decomposition
        
        Parameters
        ----------
        X : np.ndarray
            The n-dimensional tensor to fit, n>2.
        coupled_matrices : list(np.ndarray)
            The coupled matrices to fit.
        coupling_modes : list(int)
            Modes to couple along, must be ordered like coupled_matrices.
        y : None
            Ignored, included to follow sklearn standards.
        max_its : int, optional
            If set, then this will override the class's max_its
        tensor_missing_values : int or tuple(np.ndarray), optional
            Use if tensor has Nan-values. If int, imputes mean along the given axis.
            If tuple(np.ndarray), assumes these indices to be pre-imputed Nans.
        impute_matrix_axis : lis(int or None) optional
            Use if matrices has Nan. Must be same length and ordered as coupled_matrices. 
            Takes values in list and imputes means along the axis.
        penalty: float, optional
            Use if using ACMTF.
        
        Returns
        -------
        decompositions.CoupledTensors
            The decomposed tensor and matrices.
        """
        self.fit(X=X, coupled_matrices=coupled_matrices, coupling_modes=coupling_modes, y=y, max_its=max_its, tensor_missing_values=tensor_missing_values, impute_matrix_axis=impute_matrix_axis, penalty=penalty)
        return self.decomposition

    def fit(self, X, coupled_matrices, coupling_modes, y, max_its=None, tensor_missing_values=None, impute_matrix_axis=None, penalty=None):
        """Fits a CMTF model. 
        
        Parameters
        ----------
        X : np.ndarray
            The n-dimensional tensor to fit, n>2.
        coupled_matrices : list(np.ndarray)
            The coupled matrices to fit.
        coupling_modes : list(int)
            Modes to couple along, must be ordered like coupled_matrices.
        y : None
            Ignored, included to follow sklearn standards.
        max_its : int, optional
            If set, then this will override the class's max_its
        tensor_missing_values : int or tuple(np.ndarray), optional
            Use if tensor has Nan-values. If int, imputes mean along the given axis.
            If tuple(np.ndarray), assumes these indices to be pre-imputed Nans.
        impute_matrix_axis : lis(int or None) optional
            Use if matrices has Nan. Must be same length and ordered as coupled_matrices. 
            Takes values in list and imputes means along the axis.
        penalty: float, optional
            Use if using ACMTF.
        """
        self._init_fit(X=X, coupled_matrices=coupled_matrices, coupling_modes=coupling_modes, initial_decomposition=None, tensor_missing_values=tensor_missing_values, impute_matrix_axis=impute_matrix_axis, penalty=penalty)
        super()._fit()

    def init_random(self):
        """Dummy function.
        """
        pass

    def _init_fit(self, X, coupled_matrices, coupling_modes, initial_decomposition=None, max_its=None, tensor_missing_values=None, impute_matrix_axis=None, penalty=None):
        """Initialises the factorisation.
        
        Parameters
        ----------
        X : np.ndarray
            The n-dimensional tensor to fit, n>2.
        coupled_matrices : list(np.ndarray)
            The coupled matrices to fit.
        coupling_modes : list(int)
            Modes to couple along, must be ordered like coupled_matrices.
        initial_decomposition : None
            Ignored, not implemented yet.
        max_its : int, optional
            If set, then this will override the class's max_its
        tensor_missing_values : int or tuple(np.ndarray), optional
            Use if tensor has Nan-values. If int, imputes mean along the given axis.
            If tuple(np.ndarray), assumes these indices to be pre-imputed Nans.
        impute_matrix_axis : lis(int or None) optional
            Use if matrices has Nan. Must be same length and ordered as coupled_matrices. 
            Takes values in list and imputes means along the axis.
        penalty: float, optional
            Use if using ACMTF.
        """
        self.penalty = penalty
        self.missing = True if impute_matrix_axis is not None else False
        self.decomposition = self.DecompositionType.random_init(tensor_sizes=X.shape, rank=self.rank,
            matrices_sizes=[mat.shape for mat in coupled_matrices],coupling_modes=coupling_modes)
        self.coupled_matrices = coupled_matrices
        super()._init_fit(X=X, max_its=max_its, initial_decomposition=initial_decomposition, missing_values=tensor_missing_values)
        if impute_matrix_axis is not None:
        #    mats_with_missing  = [mat for mat in coupled_matrices if np.isnan(mat).any()]
            self.Ns = [np.ones(mat.shape) for mat in self.coupled_matrices]
            for i, N in enumerate(self.Ns):
                inds = np.where(np.isnan(self.coupled_matrices[i]))
                self.Ns[i][inds] = 0
            self._init_impute_matrices_missing(impute_matrix_axis)
    
    def _init_impute_matrices_missing(self, axis):
        """Mean-imputes coupled matrices with missing values (np.nan).
        
        Parameters
        ----------
        axis : list(int)
            The axes to impute a long. 
        
        Raises
        ------
        Exception
            If the number of axes is different to the number of coupled matrices.
        ValueError
            If the list of axes contains different values from 0, 1 or None.
        """
        if len(axis) != len(self.coupled_matrices):
            raise Exception("Number of matrices and axis must be the same."
                            " Got {0} matrices and {1} axis. Axis must be list of 0, 1 or None."
                            .format(len(self.coupled_matrices), len(axis)))
        if not(all(ax == 0 or ax==1 for ax in axis)):
                raise ValueError("Axis to impute along must all be either 0, 1 or None.")
        for i, axis in enumerate(axis):
            if axis is None:
                continue
            axis_means = np.nanmean(self.coupled_matrices[i], axis=axis)    
            inds = np.where(np.isnan(self.coupled_matrices[i]))  
            self.coupled_matrices[i][inds] = np.take(axis_means, inds[0 if axis==1 else 1])

    def _set_new_matrices(self):
        """Updates the coupled matrices. Does nothing if original matrix did not have missing values.
        """
        #TODO: is not used?
        for i, N in enumerate(self.Ns):
            self.coupled_matrices[i] = self.coupled_matrices[i] * N + self.reconstructed_coupled_matrices[i] * (np.ones(shape=N.shape) - N)

    def _update_als_factors(self):
        """Updates factors with alternating least squares.
        """
        num_modes = len(self.X.shape) # TODO: Should this be cashed?
        for mode in range(num_modes):
            if self.non_negativity_constraints[mode]:
                self._update_als_factor_non_negative(mode) 
            else:
                self._update_als_factor(mode)
        self._update_uncoupled_matrix_factors()
        if self.missing:
            self._set_new_matrices()
        if self.penalty:
            print('pre reguralize:', self.loss)
            self._reguralize_weights()
            print('post reguralize:', self.loss)
        #self.decomposition.reset_weights()
        
    def _reguralize_weights(self):
        self.decomposition.tensor.reset_weights()
        self.decomposition.tensor.normalize_components()
        weights = self.decomposition.tensor.weights
        A, B, C = self.factor_matrices
        l = np.zeros(self.rank)
        top = np.zeros(self.rank)
        bot = np.zeros(self.rank)
        ranks = np.arange(0, self.rank)
        for r in ranks:
            for i, j, k in itertools.product(range(A.shape[0]), range(B.shape[0]), range(C.shape[0])):
                bot[r] += (A[i, r]*B[j, r]*C[k, r])**2
                top[r] += A[i, r]*B[j, r]*C[k, r] * (self.X[i, j, k] - sum([weights[rank]*A[i, rank]*B[j, rank]*C[k, rank] for rank in ranks if rank != r]))
            
            if np.isclose(weights[r], 0):
                l[r] = top[r] / bot[r] 
            else:
                #TODO: should it be .5*penalty? does it matter?
                l[r] = (top[r] + self.penalty * (1 if abs(weights[r])>0 else -1)) / bot[r] 
        self.decomposition.tensor.weights[...] = l
        for ind, mat in enumerate(self.decomposition.matrices):
            mat.reset_weights()
            mat.normalize_components()
            weights = mat.weights
            A, V = mat.factor_matrices
            s = np.zeros(self.rank)
            top = np.zeros(self.rank)
            bot = np.zeros(self.rank)
            for r in ranks:
                for i, j in itertools.product(range(A.shape[0]), range(V.shape[0])):
                    top[r] += A[i, r]*V[j, r] * (self.coupled_matrices[ind][i, j] - sum([weights[rank]*A[i, rank]*V[j, rank] for rank in ranks if rank != r]))
                    bot[r] += (A[i, r]*V[j, r])**2

                if np.isclose(weights[r], 0):
                    s[r] = top[r] / bot[r] 
                else:
                #TODO: should it be .5*penalty? does it matter?
                    s[r] = (top[r] - self.penalty * (1 if abs(weights[r])>0 else -1)) / bot[r] 
            mat.weights = s

    def _update_als_factor(self, mode):
        """Solve least squares problem to get factor for one mode.
        """
        
        lhs = self._get_als_lhs(mode)
        rhs = self._get_als_rhs(mode)
        
        rightsolve = self._get_rightsolve(mode)
        
        new_factor = rightsolve(lhs, rhs)
        self.factor_matrices[mode][...] = new_factor
        for i, cplmode in enumerate(self.coupling_modes):
            if mode == cplmode:
                self.decomposition.matrices[i].factor_matrices[0][...] = new_factor
            
        print('cfm',mode, self.loss)

    def _get_als_lhs(self, mode):
        """Compute left hand side of least squares problem.
        """
        # TODO: make this nicer.
        if mode in self.coupling_modes:
            
            n_couplings = self.coupling_modes.count(mode)
            factors = [np.copy(mat) for mat in self.factor_matrices]
            if mode != 0:
                factors[0] = self.decomposition.tensor.weights*factors[0]
            else:
                factors[1] = self.decomposition.tensor.weights*factors[1]
            khatri_rao_product = base.khatri_rao(*factors, skip=mode)
            indices = [i for i, cplmode in enumerate(self.coupling_modes) if cplmode == mode]
            weights = [matrix.weights for matrix in self.decomposition.matrices]
            V = weights[indices[0]] * self.uncoupled_factor_matrices[indices[0]]
            if  n_couplings > 1:
                for i in indices[1:]:
                    V = np.concatenate([V, weights[i]*self.uncoupled_factor_matrices[indices[i]]], axis=0)
            return np.concatenate([khatri_rao_product, V], axis=0).T
        else:
            # V = np.ones((self.rank, self.rank))
            # TODO: this was a problem, dunno why
            # for i, factor in enumerate(self.factor_matrices):
            #     if i == mode:
            #         continue
            #     V *= (self.decomposition.tensor.weights*factor).T @ factor
            # return V
            factors = [np.copy(mat) for mat in self.factor_matrices]
            if mode != 0:
                factors[0] = self.decomposition.tensor.weights*factors[0]
            else:
                factors[1] = self.decomposition.tensor.weights*factors[1]
            return base.khatri_rao(*factors, skip=mode).T
             
    
    def _get_als_rhs(self, mode):
        """Compute right hand side of least squares problem.
        """
        if mode in self.coupling_modes:
            unfolded_X = base.unfold(self.X, mode)
            n_couplings = self.coupling_modes.count(mode)
            indices = [i for i, cplmode in enumerate(self.coupling_modes) if cplmode == mode]
            
            coupled_Y = self.coupled_matrices[indices[0]]
            if  n_couplings > 1:              
                for i in indices[1:]:
                    coupled_Y = np.concatenate([coupled_Y,
                     self.coupled_matrices[indices[i]]], axis=1)
            return np.concatenate([unfolded_X, coupled_Y], axis=1)
        else:
            #needs a fixup
            # TODO: this was a problem, dunno why
            # factors = [self.decomposition.tensor.weights * mat for mat in self.factor_matrices]
            # return base.matrix_khatri_rao_product(self.X, factors, mode)
            return base.unfold(self.X, mode)

    def _update_uncoupled_matrix_factors(self):
        """Solve ALS problem for uncoupled factor matrices.
        """
        for i, mode in enumerate(self.coupling_modes):
            lhs = (self.decomposition.matrices[i].weights*self.factor_matrices[mode]).T
            rhs = self.coupled_matrices[i].T

            if self.non_negativity_constraints is None:
                self.uncoupled_factor_matrices[i][...] = base.rightsolve(lhs, rhs)

            if self.non_negativity_constraints[mode]:
                new_fm = base.non_negative_rightsolve(lhs, rhs)
                self.uncoupled_factor_matrices[i][...] = new_fm
            else:
                self.uncoupled_factor_matrices[i][...] = base.rightsolve(lhs, rhs)
            print('ufm', mode, self.loss)

