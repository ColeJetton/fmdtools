# -*- coding: utf-8 -*-
"""
Module for creating x-y arrays to represent gridworlds.


"""
import numpy as np
import copy
from typing import ClassVar
from fmdtools.define.parameter import Parameter
from fmdtools.define.rand import Rand
from fmdtools.define.common import is_iter, get_obj_track, init_obj_dict
from fmdtools.analyze.result import History


class CoordsParam(Parameter):
    """
    Defines the underlying arrays that make up the Coords object.

    Modifiers may be added to add additional properties (e.g., features, states,
    collections, points) to the coordinates. Additionally has class fields which may be
    overwritten.

    Class Variables
    ---------------
    x_size : int
        Number of rows in the x-dimension
    y_size : int
        Number of rows in the y-dimension
    blocksize : float
        Coordinate resolution
    gapwidth : float
        Width between coordinate cells (if any). Blocksize is inclusive of this width.

    Other Modifiers
    ---------------
    feature_featurename : tuple
        Tuple (datatype, defaultvalue) defining immutable grid features to instantiate
        as arrays.
    state_statename : tuple
        Tuple (datatype, defaultvalue) defining mutable grid features to instantiate
        as arrays.
    collect_collectionname : tuple
        Tuple (propertyname, value, comparator) defining a collection of points to
        instantiate as a list, where the tuple is arguments to Coords.find_all
    point_pointname: tuple
        Tuple (x, y) referring to a point in the grid with a given name.

    Examples
    --------
    Defining the following classes will define a grid with a, v features, an
    h state, a point "start", and a "high_v" collection:

    >>> class ExampleCoordsParam(CoordsParam):
    ...     feature_a: tuple = (bool, False)
    ...     feature_v: tuple = (float, 1.0)
    ...     state_h: tuple = (float, 0.0)
    ...     point_start: tuple = (0.0, 0.0)
    ...     collect_high_v: tuple = ("v", 5.0, np.greater)
    >>> ex = ExampleCoordsParam()
    """

    x_size: ClassVar[int] = 10
    y_size: ClassVar[int] = 10
    blocksize: ClassVar[float] = 10.0
    gapwidth: ClassVar[float] = 0.0


class Coords(object):
    """
    Class for generating, accessing, and setting gridworld properties.

    Creates arrays, points, and lists of points which may correspond to desired
    modelling properties.

    Class Variables/Modifiers
    ---------------
    init_p: CoordsParam
        Parameter controlling default grid matrix (see CoordsParam), along with other
        properties of interest. Sets the .p role.
    init_r: Rand
        Random number generator. sets the .r role.
    init_properties: method
        Method that initializes the (non-default) properties of the Coords.

    Examples
    --------
    >>> class ExampleCoords(Coords):
    ...    _init_p = ExampleCoordsParam
    ...    def init_properties(self, *args, **kwargs):
    ...        self.set_pts([[0.0, 0.0], [10.0, 0.0]], "v", 10.0)

    Instantiating this class a class with (see ExampleCoordsParam):
    - immutable arrays a and v,
    - mutable array h,
    - point start at (0.0), and
    - collection high made up of all points where v > 10.0

    As shown, features are normal numpy arrays set to readonly:

    >>> ex = ExampleCoords()
    >>> type(ex.a)
    <class 'numpy.ndarray'>
    >>> np.size(ex.a)
    100
    >>> ex.a[0, 0] = True
    Traceback (most recent call last):
      ...
    ValueError: assignment destination is read-only

    The main difference with states is that they can be set, e.g.:

    >>> ex.h[0, 0] = 100.0
    >>> ex.h[0, 0]
    100.0

    Collections are lists of points that map to immutable properties. In ExampleCoords,
    all points where v > 5.0 should be a part of high_v, as shown:

    >>> ex.high_v
    array([[ 0.,  0.],
           [10.,  0.]])

    Additionally, defined points (e.g., start) should be accessible via their names:

    >>> ex.start
    (0.0, 0.0)
    """

    __slots__ = ("p", "r", "grid", "pts", "points", "collections", "features", "states",
                 "properties", "_args", "_kwargs", "default_track", )
    _init_p = CoordsParam
    _init_r = Rand

    def __init__(self, *args, **kwargs):
        """Initialize class with properties in init_properties."""
        self._args = args
        self._kwargs = kwargs
        self.init_grids(*args, **kwargs)
        self.init_properties(*args, **kwargs)
        self.build()
        if not hasattr(self, 'default_track'):
            self.default_track = self.states


    def init_grids(self, *args, **kwargs):
        """Prepare class with defined features."""
        self.p = self._init_p(**kwargs.get('p', {}))
        self.r = self._init_r(**kwargs.get('r', {}))
        self.grid = np.array([[(i, j) for j in range(0, self.p.y_size)]
                             for i in range(0, self.p.x_size)]) * self.p.blocksize
        self.pts = self.grid.reshape(int(self.grid.size/2), 2)

        init_obj_dict(self, "point", set_attr=True)
        init_obj_dict(self, "collect", "ions")
        init_obj_dict(self, "feature")
        init_obj_dict(self, "state")
        self.properties = {**self.features, **self.states}
        for propname, prop in self.properties.items():
            prop_type, prop_default = prop
            proparray = np.full((self.p.x_size, self.p.y_size),
                                prop[1], dtype=prop[0])
            setattr(self, propname, proparray)

    def init_properties(self, *args, **kwargs):
        """Initialize arrays with non-default values."""
        return 0

    def build(self):
        """Set features as immutable."""
        for propname, prop in self.properties.items():
            if propname in self.features:
                proparray = getattr(self, propname)
                proparray.flags.writeable = False
        for cname, collection in self.collections.items():
            if collection[0] in self.features:
                setattr(self, cname, self.find_all(*collection))
            else:
                raise Exception("Invalid collection: " + cname +
                                " collections may only map to (immutable) features")

    def find_all(self, name, value=True, comparator=np.equal):
        """
        Find all points in array satisfying statement defined by value and comparator.

        Parameters
        ----------
        name : str
            Name of the underlying property (state or feature).
        value : bool/float/str/etc, optional
            Value to pass to comparator. The default is True.
        comparator : function, optional
            Function to use to compare the value with the array.
            (e.g. np.equal, np.greater, np.less...). The default is np.equal.

        Returns
        -------
        all: np.array
            List of points where the comparator method returns true.

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.find_all("v", 10.0, np.equal)
        array([[ 0.,  0.],
               [10.,  0.]])
        """
        prop = getattr(self, name)
        where = np.where(comparator(prop, value))
        pts_with_condition = [(p, where[1][i]) for i, p in enumerate(where[0])]
        return np.array([self.grid[tuple(p)] for p in pts_with_condition])

    def to_index(self, *args):
        """
        Find the index of the array corresponding to the given x/y values.

        Parameters
        ----------
        *args : number, number,...
            x-y values corresponding to the scalar location of the point in the grid.

        Returns
        -------
        gridpoint: tuple
            x-y integer values corresponding to the corresponding array index.

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.to_index(10, 20)
        (1, 2)
        >>> ex.to_index(54.234, 23.41)
        (5, 2)
        """
        return tuple(round(arg/self.p.blocksize) for arg in args)

    def to_gridpoint(self, *args):
        """
        Find the closest point in the grid corresponding to the given x/y values.

        Parameters
        ----------
        *args : number, number
            x-y value corresponding to the (unrounded) scalar location in the grid

        Returns
        -------
        pt : np.array
            x-y location corresponding to the (rounded) scalar location in the grid

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.to_gridpoint(3.5, 4)
        array([0., 0.])
        >>> ex.to_gridpoint(14.0, 12.0)
        array([10., 10.])
        """
        return self.grid[self.to_index(*args)]

    def get_properties(self, x, y):
        """
        Return a dictionary of all properties (features/states) at an x-y location.

        Parameters
        ----------
        x : number
            x-location to get from.
        y : number
            y-location to get the properties from

        Returns
        -------
        properties : dict
            Dictionary of property values at the given point.

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.get_properties(0, 0)
        {'a': False, 'v': 10.0, 'h': 0.0}
        """
        properties = {}
        for prop in self.properties:
            properties[prop] = self.get(x, y, prop)
        return properties

    def get(self, x, y, prop, outside="error"):
        """
        Get the value of the property at the given scalar x/y values.

        Parameters
        ----------
        x : number
            Scalar x location
        y : number
            Scalar y location
        prop : str
            Name of the property to get.
        outside : value
            Value to provide if not in range. Default i 'error', which throws an error

        Returns
        -------
        value: int/bool/float/...
            Value to get from that point

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.get(10.0, 0.0, "v")
        10.0
        >>> ex.get(12.0, 4.9, "v")
        10.0
        >>> ex.get(50.0, 50.0, "v")
        1.0
        """
        if not self.in_range(x, y):
            if outside == "error":
                raise Exception("Outside bounds of grid: "+str(x, y))
            else:
                return outside
        proparray = getattr(self, prop)
        x_i, y_i = self.to_index(x, y)
        return proparray[x_i, y_i]

    def set(self, x, y, prop, value):
        """
        Set the value of the property at the given scalar x/y values.

        Parameters
        ----------
        x : number
            Scalar x location
        y : number
            Scalar y location
        prop : str
            Name of the property to get.
        value: int/bool/float/...
            Value to set at that point

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.set(15.0, 12.0, "h", 100.0)
        >>> ex.get(15.0, 12.0, "h")
        100.0
        """
        proparray = getattr(self, prop)
        x_i, y_i = self.to_index(x, y)
        proparray[x_i, y_i] = value

    def set_range(self, prop, value, xmin=0, xmax='max', ymin=0, ymax='max',
                  inclusive=True):
        """
        Set ranges of the grid property to a given value.

        Parameters
        ----------
        prop : str
            Name of the range
        value : value
            Value to set
        xmin : number, optional
            minimum x-value. The default is 0.
        xmax : number, optional
            maximum x-value. The default is 'max'.
        ymin : number, optional
            minimum y-value. The default is 0.
        ymax : number, optional
            maximum y-value. The default is 'max'.
        inclusive : bool, optional
            whether to include the end of the range. The default is False.

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.set_range("h", 100.0, 20, 40, 20, 40)
        >>> ex.h
        array([[  0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.],
               [  0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.],
               [  0.,   0., 100., 100., 100.,   0.,   0.,   0.,   0.,   0.],
               [  0.,   0., 100., 100., 100.,   0.,   0.,   0.,   0.,   0.],
               [  0.,   0., 100., 100., 100.,   0.,   0.,   0.,   0.,   0.],
               [  0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.],
               [  0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.],
               [  0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.],
               [  0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.],
               [  0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.,   0.]])
        >>> ex.set_range("h", 0.0)
        >>> ex.h
        array([[0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.]])
        >>> ex.set_range("h", 20.0, 20, 40, 20, 40, inclusive=False)
        >>> ex.h
        array([[ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.],
               [ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.],
               [ 0.,  0., 20., 20.,  0.,  0.,  0.,  0.,  0.,  0.],
               [ 0.,  0., 20., 20.,  0.,  0.,  0.,  0.,  0.,  0.],
               [ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.],
               [ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.],
               [ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.],
               [ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.],
               [ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.],
               [ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]])
        """
        x_min_ind, y_min_ind = self.to_index(xmin, ymin)
        if xmax == 'max':
            x_max_ind = -1
        else:
            x_max_ind, _ = self.to_index(xmax, 0.0)
            if inclusive and x_max_ind < self.p.x_size:
                x_max_ind += 1
        if ymax == 'max':
            y_max_ind = -1
        else:
            _, y_max_ind = self.to_index(0.0, ymax)
            if inclusive and y_max_ind < self.p.y_size:
                y_max_ind += 1
        proparray = getattr(self, prop)
        proparray[x_min_ind:x_max_ind, y_min_ind:y_max_ind] = value

    def set_pts(self, pts, prop, value):
        """
        Set the property to a given value over a list of provided points.

        Parameters
        ----------
        pts : list
            List of points (e.g. [(1.0, 2.0), (3.0, 4.0)]) to set.
        prop : str
            Name of the property to set.
        value : int/bool/float or list...
            Value to set the points to. Can also pass a list.

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.set_pts([(50,50), [80,80]], "h", -20.0)
        >>> ex.get(50, 50, "h")
        -20.0
        >>> ex.get(80, 80, "h")
        -20.0

        or,:

        >>> ex.set_pts([(50,50), [80,80]], "h", [-10.0, -5.0])
        >>> ex.get(50, 50, "h")
        -10.0
        >>> ex.get(80, 80, "h")
        -5.0
        """
        if is_iter(value):
            if len(value) == len(pts):
                for i, pt in enumerate(pts):
                    self.set(*pt, prop, value[i])
            else:
                raise Exception("Value " + value
                                + "doesn't match length of pts: " + pts)
        else:
            for pt in pts:
                self.set(*pt, prop, value)

    def find_closest(self, x, y, prop, include_pt=True, value=True, comparator=np.equal):
        """
        Find the closest point in the grid satisfying a given property.

        Parameters
        ----------
        x : number
            x-position to check from.
        y : number
            y-position to check from.
        prop : str
            Property or collection of the grid to check.
        include_pt : bool, optional
            Whether to include the containing grid point. The default is True.
        value : bool/int/str, optional
            Value to compare against. The default is None, which returns the points
            that have the value True.
        comparator : method, optional
            Comparator function to use (e.g., np.equal, np.greater...).
            The default is np.equal.

        Returns
        -------
        pt: np.array
            x-y position of the closest point satisfying the property.

        Examples
        --------
        Can be used with default options to check collections, e,g.:

        >>> ex = ExampleCoords()
        >>> ex.find_closest(20, 0, "high_v")
        array([10.,  0.])

        Alternatively can be used to search for the closest with a given property value,
        e.g.,:

        >>> ex.set(0, 0, "h", 1.0)
        >>> ex.find_closest(20, 0, "h", value=1.0, comparator=np.equal)
        array([0., 0.])
        """
        if prop in self.properties:
            pts = self.find_all(prop, value, comparator)
        elif prop in self.collections or prop == 'pts':
            pts = getattr(self, prop)
        else:
            raise Exception(prop+" not in .properties or .collections")
 
        p_rounded = self.to_gridpoint(x, y)

        if p_rounded.tolist() in pts.tolist():
            return p_rounded
        else:
            if not include_pt:
                pts = np.array([p for p in pts if all(p != p_rounded)])
            dists = np.sqrt(np.sum((np.array([x, y])-pts)**2, 1))
            closest_ind = np.argmin(dists)
            xy = pts[closest_ind]
            return xy

    def in_range(self, x, y):
        """
        Check to see if the x-y point is in the range of the coordinate system.

        Parameters
        ----------
        x : number
            x-position to check from.
        y : number
            y-position to check from.

        Returns
        -------
        in: bool
            Whether the point is in the range of the grid
        """
        return (0.0 <= x <= self.p.blocksize * self.p.x_size and
                0.0 <= y <= self.p.blocksize * self.p.y_size)

    def in_area(self, x, y, coll):
        """
        Check to see if the point x, y is in a given collection or at a point.

        Parameters
        ----------
        x : number
            x-position to check from.
        y : number
            y-position to check from.
       coll: str
            Property or collection of the grid to check.

        Returns
        -------
        in: bool
            Whether the point is in the collection

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.in_area(0.4, 0.2, 'start')
        True
        >>> ex.in_area(10, 10, 'start')
        False
        """
        pts = getattr(self, coll)
        if coll in self.points:
            pt = self.to_gridpoint(x, y)
            return np.all(pt == pts)
        elif coll in self.collections:
            pt = self.to_gridpoint(x, y)
            return pt in pts
        else:
            raise Exception("coll "+coll+" not a point or collection")

    def set_rand_pts(self, prop, value, number, pts=None, replace=False):
        """
        Ses a given number of points for a property to random value.

        Parameters
        ----------
        prop : str
            Property to set
        value : int/float/str/etc
            Value to set the points to
        number : int
            Number of points to set
        pts : list, optional
            List of points to select from.
            The default is None (which selects from all points).
        replace : bool, optional
            Whether to select with replacement. The default is False.

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.set_rand_pts("h", 40, 5)
        >>> len(ex.find_all("h", 40))
        5
        """
        if pts is None:
            pts = self.pts
        else:
            pts = pts
        set_pts = self.r.rng.choice(pts, number, replace=replace)
        self.set_pts(set_pts, prop, value)

    def set_prop_dist(self, prop, dist, *args, **kwargs):
        """
        Randomizes a property according to a given distribution.

        Parameters
        ----------
        prop : str
            Property to set
        dist : str
            Name of distribution to call from the rng.
            (see documentation for numpy.random)
        *args : tuple, optional
            Arguments to the distribution method (e.g., (min, max)). The default is ().
        **kwargs : kwargs, optional
            Keyword arguments to the distribution method. The default is {}.
        """
        p = getattr(self, prop)
        meth = getattr(self.r.rng, dist)
        new_p = meth(*args, size=p.shape, **kwargs)
        setattr(self, prop, new_p)

    def return_mutables(self):
        """Check if grid properties have changed (used in propagation)."""
        return tuple([*(tuple(map(tuple, getattr(self, state))) for state in self.states)])

    def copy(self):
        """
        Copy the Coords object.

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> ex.set(0, 0, "h", 25.0)
        >>> cop = ex.copy()
        >>> cop.get(0, 0, "h")
        25.0
        >>> np.all(ex.h == cop.h)
        True
        >>> id(ex.h) == id(cop.h)
        False
        """
        cop = self.__class__(*self._args, **self._kwargs)
        for state in self.states:
            setattr(cop, state, np.copy(getattr(self, state)))
        return cop

    def create_hist(self, timerange, track):
        """
        Create a history of states for the Coords object.

        Parameters
        ----------
        timerange : iterable, optional
            Time-range to initialize the history over. The default is None.
        track : list/str/dict, optional
            argument specifying attributes for :func:`get_sub_include'.
            The default is None.

        Returns
        -------
        hist : History
            History of fields specified in track.

        Examples
        --------
        >>> ex = ExampleCoords()
        >>> h = ex.create_hist([0, 1, 2], "all")
        >>> h.keys()
        dict_keys(['h'])
        >>> h.h[0]
        array([[0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
               [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.]])
        """
        track = get_obj_track(self, track, all_possible=self.states)
        h = History()
        for att in track:
            val = getattr(self, att)
            h.init_att(att, val, timerange, track, dtype=np.ndarray)
        return h

    def get_collection(self, prop):
        """
        Get the points for a given collection.

        Parameters
        ----------
        prop : str
            Name of the collection.

        Returns
        -------
        coll: np.ndarray
            Array of points in the collection
        """
        if prop in self.collections or prop == 'pts':
            return getattr(self, prop)
        elif prop in self.points:
            return np.array([getattr(self, prop)])
        else:
            raise Exception("Not a point or collection")

    def return_states(self):
        """Return the mutable states of a Coords object."""
        states = dict.fromkeys(self.states)
        for state in states:
            states[state] = copy.copy(getattr(self, state))
        return states

class ExampleCoordsParam(CoordsParam):
    """Example of a Coords param for use in documentation/testing."""

    feature_a: tuple = (bool, False)
    feature_v: tuple = (float, 1.0)
    state_h: tuple = (float, 0.0)
    point_start: tuple = (0.0, 0.0)
    collect_high_v: tuple = ("v", 5.0, np.greater)


class ExampleCoords(Coords):
    """Example of Coords class for use in documentation and testing."""

    _init_p = ExampleCoordsParam

    def init_properties(self, *args, **kwargs):
        """Initialize points where v=10.0."""
        self.set_pts([[0.0, 0.0], [10.0, 0.0]], "v", 10.0)


if __name__ == "__main__":
    ex = ExampleCoords()
    import doctest
    doctest.testmod(verbose=True)
