from __future__ import division

import warnings
from itertools import product
import numpy as np

# TODO: Incorporate @pablodecm's cover API.


class Cover:
    """Helper class that defines the default covering scheme

    It calculates the cover based on the following formula for overlap.     (https://arxiv.org/pdf/1706.00204.pdf)

                     |cube[i] intersection cube[i+1]|
        overlap = --------------------------------------
                              |cube[i]|
    

    Parameters
    ------------

    n_cubes: int 
        Number of hypercubes along each dimension. Sometimes referred to as resolution.

    perc_overlap: float
        Amount of overlap between adjacent cubes calculated only along 1 dimension.

    limits: Numpy Array (n_dim,2)
        (lower bound, upper bound) for every dimension
        If a value is set to `np.float('inf')`, the bound will be assumed to be the min/max value of the dimension
        Also, if `limits == None`, the limits are defined by the maximum and minimum value of the lens for all dimensions.
        i.e. `[[min_1, max_1], [min_2, max_2], [min_3, max_3]]`
    
    Example
    ---------

    ::

        >>> import numpy as np
        >>> from kmapper.cover import Cover
        >>> data = np.random.random((100,2))
        >>> cov = Cover(n_cubes=15, perc_overlap=0.75)
        >>> coordinates = cov.define_bins(data)
        >>> cov.find_entries(data, coordinates[0])
        array([[0.3594448 , 0.07428465],
               [0.14490332, 0.01395559],
               [0.94988668, 0.03983579],
               [0.73517978, 0.09420806],
               [0.16903735, 0.06901085],
               [0.81578595, 0.10708731],
               [0.26923572, 0.12216203],
               [0.89203167, 0.0711279 ],
               [0.80442115, 0.10220901],
               [0.33210782, 0.04365007],
               [0.52207707, 0.05892861],
               [0.26589744, 0.08502856],
               [0.02360067, 0.1263653 ],
               [0.29855631, 0.01209373]])


    """

    def __init__(
        self,
        n_cubes=10,
        perc_overlap=0.2,
        limits=None,
        # Deprecated parameters:
        nr_cubes=None,
        overlap_perc=None
    ):

        self.n_cubes = nr_cubes if nr_cubes else n_cubes
        self.perc_overlap = overlap_perc if overlap_perc else perc_overlap

        if overlap_perc is not None or nr_cubes is not None:
            warnings.warn(
                "Arguments `overlap_perc` and `nr_cubes` have been replaced with `perc_overlap` and `n_cubes`. Use `perc_overlap` and `n_cubes` instead. They will be removed in future releases.",
                DeprecationWarning,
            )

        self.limits = limits

        # Check limits can actually be handled and are set appropriately
        NoneType = type(None)
        assert isinstance(
            self.limits, (list, np.ndarray, type(None))
        ), "limits should either be an array or None"
        if isinstance(self.limits, (list, np.ndarray)):
            self.limits = np.array(self.limits)
            assert self.limits.shape[1] == 2, "limits should be (n_dim,2) in shape"

    def define_bins(self, data):
        """Returns an iterable of all bins in the cover.

        Warning: This function must assume that the first column of data are indices.
        
        Examples
        ---------

            If there are 4 cubes per dimension and 3 dimensions return the bottom left (origin) coordinates of 64 hypercubes, as a sorted list of Numpy arrays
        """

        indexless_data = data[:, 1:]

        # Find upper and lower bounds of bins using self.limits
        # If array, use the values in the array
        # If None, use the maximum and minimum values in the lens

        # If self.limits is array-like
        if isinstance(self.limits, np.ndarray):
            # limits_array is used so we can change the values of self.limits from None to the min/max
            limits_array = np.zeros(self.limits.shape)
            limits_array[:, 0] = np.min(indexless_data, axis=0)
            limits_array[:, 1] = np.max(indexless_data, axis=0)
            limits_array[self.limits != np.float("inf")] = 0
            self.limits[self.limits == np.float("inf")] = 0
            bounds_arr = self.limits + limits_array
            """ bounds_arr[i,j] = self.limits[i,j] if self.limits[i,j] == inf
                bounds_arr[i,j] = max/min(indexless_data[i]) if self.limits == inf """
            bounds = (bounds_arr[:, 0], bounds_arr[:, 1])

            # Check new bounds are actually sensible - do they cover the range of values in the dataset?
            if not (
                (np.min(indexless_data, axis=0) >= bounds_arr[:, 0]).all()
                or (np.max(indexless_data, axis=0) <= bounds_arr[:, 1]).all()
            ):
                warnings.warn(
                    "The limits given do not cover the entire range of the lens functions\n"
                    + "Actual Minima: %s\tInput Minima: %s\n"
                    % (np.min(indexless_data, axis=0), bounds_arr[:, 0])
                    + "Actual Maxima: %s\tInput Maxima: %s\n"
                    % (np.max(indexless_data, axis=0), bounds_arr[:, 1])
                )

        else:  # It must be None, as we checked to see if it is array-like or None in __init__
            bounds = (np.min(indexless_data, axis=0), np.max(indexless_data, axis=0))

        # We chop up the min-max column ranges into 'n_cubes' parts
        self.base_dist = (bounds[1] - bounds[0]) / self.n_cubes

        # We calculate the overlapping windows distance
        self.overlap_dist = self.perc_overlap * self.base_dist
        
        # Chunk dist is the combination of the base dist along with what it gets from the overlap on each side
        self.chunk_dist = self.base_dist + self.overlap_dist*2

        # We find our starting point
        self.d = bounds[0]
        
        # And our ending point (for testing)
        self.end = bounds[1]

        # Use a dimension index array on the projected X
        # (For now this uses the entire dimensionality, but we keep for experimentation)
        self.di = np.array(range(1, data.shape[1]))
        self.nr_dimensions = len(self.di)

        if type(self.n_cubes) is not list:
            cubes = [self.n_cubes] * self.nr_dimensions
        else:
            assert (
                len(self.n_cubes) == self.nr_dimensions
            ), "There are {} ({}) dimensions specified but {} dimensions needing specification. If you supply specific number of cubes for each dimension, please supply the correct number.".format(
                len(self.n_cubes), self.n_cubes, self.nr_dimensions
            )
            cubes = self.n_cubes

        coordinates = list(map(np.asarray, product(*(range(i) for i in cubes))))
        return coordinates

    def find_entries(self, data, cube, verbose=0):
        """Find all entries in data that are in the given cube.

        Parameters
        ----------
        data: Numpy array
            Either projected data or original data.
        cube:
            an item from the list of cubes provided by `cover.define_bins` iterable.

        Returns
        -------
        hypercube: Numpy Array
            All entries in data that are in cube.

        """

        base = self.base_dist
        overlap = self.overlap_dist
        chunk = self.chunk_dist
        
        lower_bound_unclipped = self.d + (cube * base) - overlap
        upper_bound_unclipped = lower_bound_unclipped + chunk
        
        lower_bound = np.clip(lower_bound_unclipped, a_min=self.d, a_max=self.end)
        upper_bound = np.clip(upper_bound_unclipped, a_min=self.d, a_max=self.end)
        

        # Slice the hypercube
        entries = (data[:, self.di] >= lower_bound) & (data[:, self.di] <= upper_bound)

        hypercube = data[np.invert(np.any(entries == False, axis=1))]

        return hypercube


class CubicalCover(Cover):
    """
    Explicit definition of a cubical cover as the default behavior of the cover class. This is currently identical to the default cover class.
    """

    pass
