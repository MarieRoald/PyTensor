from copy import copy
from pathlib import Path
import h5py
import numpy as np

from .. import base
from .cp import get_sse_lhs
from .parafac2 import BaseParafac2, compute_projected_X, Parafac2_ALS
from .decompositions import KruskalTensor, Parafac2Tensor
from .base_decomposer import BaseDecomposer
from . import decompositions
from .. import utils


class BaseSubProblem:
    def __init__(self):
        pass

    def update_decomposition(self, X, decomposition):
        pass

    def regulariser(self, factor) -> float:
        return 0


class RLS(BaseSubProblem):
    def __init__(self, mode, ridge_penalty=0, non_negativity=False):
        self.ridge_penalty = ridge_penalty
        self.non_negativity = non_negativity
        self.mode = mode
        self._matrix_khatri_rao_product_cache = None
    
    def update_decomposition(self, X, decomposition):
        lhs = get_sse_lhs(decomposition.factor_matrices, self.mode)
        rhs = base.matrix_khatri_rao_product(X, decomposition.factor_matrices, self.mode)

        self._matrix_khatri_rao_product_cache = rhs

        rightsolve = self._get_rightsolve()

        decomposition.factor_matrices[self.mode][:] = rightsolve(lhs, rhs)
    
    def _get_rightsolve(self):
        rightsolve = base.rightsolve
        if self.non_negativity:
            rightsolve = base.non_negative_rightsolve
        if self.ridge_penalty:
            rightsolve = base.add_rightsolve_ridge(rightsolve, self.ridge_penalty)
        return rightsolve


def prox_reg_lstsq(A, B, reg, C, D):
    """Solve ||AX - B||^2 + r||CX - D||^2
    """
    # We can save much time here by storing a QR decomposition of A_new.
    reg = np.sqrt(reg/2)
    A_new = np.concatenate([A, reg*C], axis=0)
    B_new = np.concatenate([B, reg*D], axis=0)
    return np.linalg.lstsq(A_new, B_new)[0]


class ADMMSubproblem(BaseSubProblem):
    def __init__(self, mode, rho, tol=1e-3, max_it=50, non_negativity=True):
        self.non_negativity = non_negativity
        self.rho = rho
        self.mode = mode
        self.tol = tol
        self.max_it = max_it

    
    def update_decomposition(self, X, decomposition):
        # TODO: Cache QR decomposition of lhs.T
        # ||MA - X||
        # M = lhs
        # X = rhs
        lhs = base.khatri_rao(
            *decomposition.factor_matrices, skip=self.mode
        ).T
        rhs = base.unfold(X, self.mode)

        # Assign name to current factor matrix to and identity reduce space
        fm = decomposition.factor_matrices[self.mode]
        I = np.identity(fm.shape[1])
        
        # Initialise main variable by unregularised least squares,
        # auxiliary variable by projecting main variable init
        # and the dual variable as zeros
        fm[:] = np.linalg.lstsq(lhs.T, rhs.T)[0].T
        aux_fm = self.init_aux_factor_matrix(decomposition)
        dual_variable = np.zeros_like(fm)

        # Update decomposition and auxiliary variable with proximal
        # map calls followed by a gradient ascent step for the dual
        # variable. Stop if main and aux variable are close enough
        for _ in range(self.max_it):
            if self.has_converged(fm, aux_fm):
                break
            fm[:] = prox_reg_lstsq(lhs.T, rhs.T, self.rho/2, I, aux_fm.T - dual_variable.T).T
            self.update_constraint(decomposition, aux_fm, dual_variable)

            dual_variable += fm - aux_fm
        
        # Use aux variable for hard constraints
        decomposition.factor_matrices[self.mode][:] = aux_fm
    
    def init_aux_factor_matrix(self, decomposition):
        """Initialise the auxiliary factor matrix used to fit the constraints.
        """
        return np.maximum(decomposition.factor_matrices[self.mode], 0)
    
    def update_constraint(self, decomposition, aux_fm, dual_variable):
        """Update the auxiliary factor matrix used to fit the constraints inplace.
        """
        np.maximum(
            decomposition.factor_matrices[self.mode] + dual_variable,
            0,
            out=aux_fm
        )
    
    def has_converged(self, fm, aux_fm):
        return np.linalg.norm(fm - aux_fm) < self.tol


class BaseParafac2SubProblem(BaseSubProblem):
    _is_pf2_evolving_mode = True
    mode = 1
    def __init__(self):
        pass

    def minimise(self, X, decomposition, projected_X=None, should_update_projections=True):
        pass


class Parafac2RLS(BaseParafac2SubProblem):
    def __init__(self, ridge_penalty=0):
        self.ridge_penalty = ridge_penalty
        self.non_negativity = False

    def compute_projected_X(self, projection_matrices, X, out=None):
        return compute_projected_X(projection_matrices, X, out=out)

    def update_projections(self, X, decomposition):
        K = len(X)

        for k in range(K):
            A = decomposition.A
            C = decomposition.C
            blueprint_B = decomposition.blueprint_B

            decomposition.projection_matrices[k][:] = base.orthogonal_solve(
                (C[k]*A)@blueprint_B.T,
                X[k]
            ).T

    def update_decomposition(
        self, X, decomposition, projected_X=None, should_update_projections=True
    ):
        """Updates the decomposition inplace

        If a projected data tensor is supplied, then it is updated inplace
        """
        if should_update_projections:
            self.update_projections(X, decomposition)
            projected_X = self.compute_projected_X(decomposition.projection_matrices, X, out=projected_X)
        
        if projected_X is None:
            projected_X = self.compute_projected_X(decomposition.projection_matrices, X, out=projected_X)
        ktensor = KruskalTensor([decomposition.A, decomposition.blueprint_B, decomposition.C])
        RLS.update_decomposition(self, X=projected_X, decomposition=ktensor)

    def _get_rightsolve(self):
        return RLS._get_rightsolve(self)


class Parafac2ADMM(BaseParafac2SubProblem):
    # In our notes: U -> dual variable
    #               \tilde{B} -> aux_fms
    #               B -> decomposition
    def __init__(self, rho, tol=1e-3, max_it=50, non_negativity=False, verbose=False):
        if rho is None:
            self.auto_rho = True
        else:
            self.auto_rho = False

        self.rho = rho
        self.tol = tol
        self.max_it = max_it
        self.non_negativity = non_negativity
        self.verbose = verbose
        self._qr_cache = None
    
    def update_decomposition(
        self, X, decomposition, projected_X=None, should_update_projections=True
    ):
        self._qr_cache = None
        if self.auto_rho:
            self.rho, self._qr_cache = self.compute_auto_rho(decomposition)
        # Init constraint by projecting the decomposition
        aux_fms = self.init_constraint(decomposition.projection_matrices, decomposition.blueprint_B)
        dual_variables = [np.zeros_like(aux_fm) for aux_fm in aux_fms]
        for i in range(self.max_it):
            if should_update_projections:
                self.update_projections(X, decomposition, aux_fms, dual_variables)
                projected_X = self.compute_projected_X(decomposition.projection_matrices, X, out=projected_X)
            
            if projected_X is None:
                projected_X = self.compute_projected_X(decomposition.projection_matrices, X, out=projected_X)

            self.update_blueprint(X, decomposition, aux_fms, dual_variables, projected_X)
            self.has_converged(decomposition, aux_fms)
            self.update_constraint(decomposition, aux_fms, dual_variables)
            self.update_dual(decomposition, aux_fms, dual_variables)

    def compute_auto_rho(self, decomposition):     
        lhs = base.khatri_rao(
            decomposition.A, decomposition.C,
        )
        rho = np.linalg.norm(lhs)**2/decomposition.rank

        reg_lhs = np.vstack([np.identity(decomposition.rank) for _ in decomposition.B])
        reg_lhs *= np.sqrt(rho/2)
        lhs = np.vstack([lhs, reg_lhs])

        return rho, np.linalg.qr(lhs)

    def init_constraint(self, init_P, init_B):
        B = [P_k@init_B for P_k in init_P]
        if self.non_negativity:
            return [np.maximum(B_k, 0, out=B_k) for B_k in B]
        else:
            return B

    def update_constraint(self, decomposition, aux_fms, dual_variables):
        projections = decomposition.projection_matrices
        blueprint_B = decomposition.blueprint_B
        aux_fms = [
            self.prox_update(
                P_k@blueprint_B + dual_variables[k], out=aux_fm
            ) for k, (P_k, aux_fm) in enumerate(zip(projections, aux_fms))
        ]
    
    def prox_update(self, x, out):
        if not self.non_negativity:
            out[:] = x
        else:
            np.maximum(x, 0, out=out)

    def update_dual(self, decomposition, aux_fms, dual_variables):
        for P_k, aux_fm, dual_variable in zip(decomposition.projection_matrices, aux_fms, dual_variables):
            B_k = P_k@decomposition.blueprint_B
            dual_variable -= B_k - aux_fm

    def update_projections(self, X, decomposition, aux_fms, dual_variable):
        # Triangle equation from notes
        A = decomposition.A
        blueprint_B = decomposition.blueprint_B
        C = decomposition.C
        for k, X_k in enumerate(X):
            unreg_lhs = (A*C[k])@(blueprint_B.T)
            reg_lhs = np.sqrt(self.rho/2)*(blueprint_B.T)
            lhs = np.vstack((unreg_lhs, reg_lhs))

            unreg_rhs = X_k
            reg_rhs = np.sqrt(self.rho/2)*(aux_fms[k] - dual_variable[k]).T
            rhs = np.vstack((unreg_rhs, reg_rhs))
            
            decomposition.projection_matrices[k][:] = base.orthogonal_solve(lhs, rhs).T

    def update_blueprint(self, X, decomposition, aux_fms, dual_variables, projected_X):
        # Square equation from notes
        if self._qr_cache is None:
            lhs = base.khatri_rao(
                decomposition.A, decomposition.C,
            )
            reg_lhs = np.vstack([np.identity(decomposition.rank) for _ in aux_fms])
            reg_lhs *= np.sqrt(self.rho/2)
            lhs = np.vstack([lhs, reg_lhs])
            self._qr_cache = np.linalg.qr(lhs)
        Q, R = self._qr_cache
        
        rhs = base.unfold(projected_X, 1).T
        projected_aux = [
            (aux_fm - dual_variable).T@projection
            for aux_fm, dual_variable, projection in zip(
                aux_fms, dual_variables, decomposition.projection_matrices
            )
        ]
        reg_rhs = np.vstack(projected_aux)
        reg_rhs *= np.sqrt(self.rho/2)
        rhs = np.vstack([rhs, reg_rhs])

        decomposition.blueprint_B[:] = np.linalg.solve(R, Q.T@rhs).T
        #decomposition.blueprint_B[:] = prox_reg_lstsq(lhs, rhs, self.rho, reg_lhs, reg_rhs).T
    
    def compute_projected_X(self, projection_matrices, X, out=None):
        return compute_projected_X(projection_matrices, X, out=out)

    def _duality_gap(self, fms, aux_fms):
        return sum(np.linalg.norm(fm - aux_fm)**2 for fm, aux_fm in zip(fms, aux_fms))

    def has_converged(self, decomposition, aux_fms):
        fms = [P@decomposition.blueprint_B for P in decomposition.projection_matrices]
        e = self._duality_gap(fms, aux_fms)
        if self.verbose:
            print(e)
        return e < self.tol
        


class FlexibleParafac2ADMM(BaseParafac2SubProblem):
    def __init__(self, non_negativity=True):
        self.non_negativity = non_negativity

    def update_decomposition(self,  X, decomposition, projected_X, update_projections):
        pass

class BlockParafac2(BaseDecomposer):
    DecompositionType = decompositions.Parafac2Tensor
    def __init__(
        self,
        rank,
        sub_problems,
        max_its=1000,
        convergence_tol=1e-6,
        init='random',
        loggers=None,
        checkpoint_frequency=None,
        checkpoint_path=None,
        print_frequency=None,
        projection_update_frequency=5,
    ):
        if (
            not hasattr(sub_problems[1], '_is_pf2_evolving_mode') or 
            not sub_problems[1]._is_pf2_evolving_mode
        ):
            raise ValueError(
                'Second sub problem must follow PARAFAC2 constraints. If it does, '
                'ensure that `sub_problem._is_pf2 == True`.'
            )

        super().__init__(
            max_its=max_its,
            convergence_tol=convergence_tol,
            loggers=loggers,
            checkpoint_frequency=checkpoint_frequency,
            checkpoint_path=checkpoint_path,
            print_frequency=print_frequency,
        )
        self.rank = rank
        self.sub_problems = sub_problems
        self.init = init
        self.projection_update_frequency = projection_update_frequency

    def _check_valid_components(self, decomposition):
        return BaseParafac2._check_valid_components(self, decomposition)

    @property
    def loss(self):
        factor_matrices = [
            self.decomposition.A,
            (self.decomposition.projection_matrices,
            self.decomposition.B), self.decomposition.C
        ]
        return (
            self.SSE + 
            sum(sp.regulariser(fm) for sp, fm in zip(self.sub_problems, factor_matrices))
        )

    def _update_parafac2_factors(self):
        should_update_projections = self.current_iteration % self.projection_update_frequency == 0
        # The function below updates the decomposition and the projected X inplace.
        #print(f'{self.current_iteration:6d}A: The MSE is {self.MSE:4g}, f is {self.loss:4g}, '
        #              f'improvement is {self._rel_function_change:g}')
        self.sub_problems[1].update_decomposition(
            self.X, self.decomposition, self.projected_X, should_update_projections=should_update_projections
        )
        #print(f'{self.current_iteration:6d}B: The MSE is {self.MSE:4g}, f is {self.loss:4g}, '
        #              f'improvement is {self._rel_function_change:g}')
        self.sub_problems[0].update_decomposition(
            self.projected_X, self.cp_decomposition
        )
        #print(f'{self.current_iteration:6d}C: The MSE is {self.MSE:4g}, f is {self.loss:4g}, '
        #              f'improvement is {self._rel_function_change:g}')
        self.sub_problems[2].update_decomposition(
            self.projected_X, self.cp_decomposition
        )

    def _fit(self):
        for it in range(self.max_its - self.current_iteration):
            if self._rel_function_change < self.convergence_tol:
                break

            self._update_parafac2_factors()
            self._update_convergence()

            if self.current_iteration % self.print_frequency == 0 and self.print_frequency > 0:
                print(f'{self.current_iteration:6d}: The MSE is {self.MSE:4g}, f is {self.loss:4g}, '
                      f'improvement is {self._rel_function_change:g}')

            self._after_fit_iteration()


        if (
            ((self.current_iteration+1) % self.checkpoint_frequency != 0) and 
            (self.checkpoint_frequency > 0)
        ):
            self.store_checkpoint()

    def init_components(self, initial_decomposition=None):
        BaseParafac2.init_components(self, initial_decomposition=initial_decomposition)

    def _update_convergence(self):
        return Parafac2_ALS._update_convergence(self)

    def _init_fit(self, X, max_its, initial_decomposition):
        super()._init_fit(X=X, max_its=max_its, initial_decomposition=initial_decomposition)
        self.cp_decomposition = KruskalTensor(
            [self.decomposition.A, self.decomposition.blueprint_B, self.decomposition.C]
        )
        self.projected_X = compute_projected_X(self.decomposition.projection_matrices, self.X)
        self.prev_loss = self.loss
        self._rel_function_change = np.inf
    
    def init_random(self):
        return BaseParafac2.init_random(self)
    
    def init_svd(self):
        return BaseParafac2.init_svd(self)

    def init_cp(self):
        return BaseParafac2.init_cp(self)

    @property
    def reconstructed_X(self):
        return self.decomposition.construct_slices()
    
    def set_target(self, X):
        BaseParafac2.set_target(self, X)

    @property
    def SSE(self):
        return utils.slice_SSE(self.X, self.reconstructed_X)

    @property
    def MSE(self):
        return self.SSE/self.decomposition.num_elements