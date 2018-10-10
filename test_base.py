import numpy as np
from pytest import fixture, approx
import base 

np.random.seed(0)

#---------------- Fixtures ----------------#
@fixture
def random_tensor():
    return np.random.random((2, 2, 2))
@fixture
def random_matrix():
    return np.random.random((2, 2))

@fixture
def random_factors():
    rank = 2
    sizes = [5, 3, 10]
    factors = []
    for size in sizes:
        factors.append(np.random.random((size, rank)))

    return factors
    
#----------------- Tests ------------------#
def test_unfold_inverted_by_fold(random_tensor):
    for i in range(len(random_tensor.shape)):
        assert np.array_equal(random_tensor, base.fold(base.unfold(random_tensor, i), i, random_tensor.shape))

def test_flatten_inverted_by_unflatten(random_factors):
    rank = random_factors[0].shape[1]
    sizes = [factor.shape[0] for factor in random_factors]
    unflattened_factors = base.unflatten_factors(base.flatten_factors(random_factors), rank, sizes)
    
    for random_factor, flattened_factor in zip(random_factors, unflattened_factors):
        assert np.array_equal(random_factor, flattened_factor)