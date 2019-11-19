# TensorKit
## Tensor learning in Python

TensorKit offers a scikit-learn like API to tensor learning in Python. 

Currently, we support CP and PARAFAC2 decomposition using alternating least squares and we are working on coupled decompositions.

Note that the code is still under development so the API may be subject to change.

TensorKit is created by Marie Roald and Yngve Mardal Moe.

## Why not just use TensorLy

TensorLy is a good way into providing tensor learning in Python, however, we found that taking a more object-oriented approach was more useful when conducting many experiments. Also, it should be easier to start using TensorKit for people who have experience with scikit-learn.

## Installation

To install the latest version, run the following commands

```bash
git clone https://github.com/marieroald/tensorkit
cd TensorKit
python setup.py
```

## Example

Below is an example where we create a random Kruskal tensor and decompose it using the CP decomposition.

```python
import numpy as np
from tenkit.decomposition import decompositions
from tenkit.decomposition.cp import CP_ALS

# Generate random tensor    
shape = (30, 40, 50)
rank = 4
random_tensor = decompositions.KruskalTensor.random_init(shape, rank)

# Add noise    
noise_level = 0.3
tensor = random_tensor.construct_tensor()
noise = np.random.standard_normal(tensor.shape)
noise *= noise_level*np.linalg.norm(tensor)/np.linalg.norm(noise)
noisy_tensor = tensor + noise

# Fit a CP model
cp = CP_ALS(rank)
learned_decomposition = cp.fit_transform(noisy_tensor)

# Evaluate performance
fms, permutation = random_tensor.factor_match_score(learned_decomposition)
print(f'The factor match score is {fms:.3e} and the factor permutation is {permutation}')
```
