# -*- coding: utf-8 -*-
"""
Description: A module for defining Parameters, which are (generic) containers for
system attributes that do not change.

- :class:`Parameter`: Superclass for Parameters
- :class:`SimParam`: Class defining Simulation Parameters
"""

import inspect
from recordclass import dataobject, asdict
import warnings
import numpy as np

from .common import get_true_fields, get_true_field


class Parameter(dataobject, readonly=True, mapping=True, iterable=True):
    """
    The Parameter class defines model/function/flow values which are immutable,
    that is, the same from model instantiation through a simulation. Parameters
    inherit from recordclass, giving them a low memory footprint, and use type
    hints and ranges to ensure parameter values are valid. e.g.,:

    >>> class Param(Parameter, readonly=True):
    ...     x: float = 30.0
    ...     y:          float = 30.0
    ...     x_lim = (0.0,100.0)
    ...     y_set = (0.0,30.0,100.0)

    defines a parameter with float x and y fields with default values of 30 and
    x_lim minimum/maximum values for x and y_set possible values for y. Note that
    readonly=True should be set to ensure fields are not changed.

    This parameter can then be instantiated using:

    >>> p = Param(x=1.0, y=0.0)
    >>> p.x
    1.0
    >>> p.y
    0.0
    """

    def __init__(self, *args, strict_immutability=True, check_type=True,
                 check_pickle=True, **kwargs):
        """
        Initializes the parameter with given kwargs.

        Parameters
        ----------
        strict_immutability : bool
            Performs basic checks to ensure fields are immutable

        **kwargs : kwargs
            Fields to set to non-default values.
        """
        if not self.__doc__:
            raise Exception("Please provide docstring")
            # self.__doc__=Parameter.__doc__
        for k, v in kwargs.items():
            self.check_lim(k, v)
        try:
            super().__init__(*args, **kwargs)
        except TypeError:
            raise Exception("Invalid args/kwargs: "+str(args)+" , " +
                            str(kwargs)+" in "+str(self.__class__))
        if strict_immutability:
            self.check_immutable()
        if check_type:
            self.check_type()
        if check_pickle:
            self.check_pickle()

    def keys(self):
        return self.__fields__

    def check_lim(self, k, v):
        """
        Checks to ensure the value v for field k is within the defined limits
        self.k_lim or set constraints self.k_set

        Parameters
        ----------
        k : str
            Field to check
        v : mutable
            Value for the field to check

        Raises
        ------
        Exception
            Notification that the field is outside limits/set constraints.
        """
        var_lims = getattr(self, k+"_lim", False)
        if var_lims:
            if not (var_lims[0] <= v <= var_lims[1]):
                raise Exception("Variable "+k+" ("+str(v) +
                                ") outside of limits: "+str(var_lims))
        var_set = getattr(self, k+"_set", False)
        if var_set:
            if not (v in var_set):
                raise Exception("Variable "+k+" ("+str(v) +
                                ") outside of set constraints: "+str(var_set))

    def check_immutable(self):
        """
        (woefully incomplete) check to ensure defined field values are immutable.
        Checks if a known/common mutable or a known/common immutable, otherwise
        gives a warning.

        Raises
        ------
        Exception
            Throws exception if a known mutable (e.g., dict, set, list, etc)
        """
        for f in self.__fields__:
            attr = getattr(self, f)
            attr_type = type(attr)
            if isinstance(attr, (list, set, dict)):
                raise Exception("Parameter "+f+" type "+str(attr_type)+" is mutable")
            elif isinstance(attr, np.ndarray):
                attr.flags.writeable = False
            elif not isinstance(attr, (int, float, tuple, str, Parameter, np.number)):
                warnings.warn("Parameter "+f+" type "+str(attr_type)+" may be mutable")

    def check_type(self):
        """
        Checks to ensure Parameter type-hints are being followed.

        Raises
        ------
        Exception
            Raises exception if a field is not the same as its defined type.
        """
        for typed_field in self.__annotations__:
            attr_type = type(getattr(self, typed_field))
            true_type = self.__annotations__.get(typed_field, False)
            if ((true_type and not attr_type == true_type) and
                    str(true_type).split("'")[1] not in str(attr_type)):
                # weaker, but enables use of np.str, np.float, etc
                raise Exception(typed_field+" in "+str(self.__class__) +
                                " assigned incorrect type: " + str(attr_type) +
                                " (should be "+str(true_type)+")")

    def copy_with_vals(self, **kwargs):
        """Creates a copy of itself with modified values given by kwargs"""
        return self.__class__(**{**asdict(self), **kwargs})

    def check_pickle(self):
        """Checks to make sure pickled object will get *args and **kwargs"""
        signature = str(inspect.signature(self.__init__))
        if not ('*args' in signature) and ('**kwargs' in signature):
            raise Exception("*args and **kwargs not in __init__()--will not pickle.")

    def get_true_field(self, fieldname, *args, **kwargs):
        return get_true_field(self, fieldname, *args, **kwargs)

    def get_true_fields(self, *args, **kwargs):
        return get_true_fields(self, *args, **kwargs)


class SimParam(Parameter, readonly=True):
    """
    Class defining Simulation parameters.

    Has fields:
        phases : tuple
            phases (('name', start, end)...) that the simulation progresses through
        times : tuple
            tuple of times to sample (if desired)
            (starttime, sampletime1, sampletime2,... endtime)
        dt : float
            timestep used in the simulation. default is 1.0
        units : str
            time-units. default is hours`
        end_condition : str
            Name of indicator method to use to end the simulation. If not provided (''),
            the simulation ends at the final time. Default is ''
        use_local : bool
            Whether to use locally-defined timesteps in functions (if any).
            Default is True.
    """
    phases:            tuple = (('na', 0, 100),)
    times:             tuple = (0, 100)
    dt:                float = 1.0
    units:             str = "hr"
    units_set = ('sec', 'min', 'hr', 'day', 'wk', 'month', 'year')
    end_condition:     str = ''
    use_local:         bool = True

    def __init__(self, *args, **kwargs):
        if ('times' in kwargs) and not ('phases' in kwargs):
            kwargs['phases'] = (("na", 0, kwargs['times'][-1]),)
        super().__init__(*args, **kwargs)
        self.find_any_phase_overlap()

    def find_any_phase_overlap(self):
        phase_dict = {v[0]: [v[1], v[2]] for v in self.phases}
        intervals = [*phase_dict.values()]
        int_low = np.sort([i[0] for i in intervals])
        int_high = np.sort([i[1] if len(i) == 2 else i[0] for i in intervals])
        for i, il in enumerate(int_low):
            if i+1 == len(int_low):
                break
            if int_low[i+1] <= int_high[i]:
                raise Exception("Global phases overlap in " + self.__class__.__name__ +
                                ": " + str(self.phases) +
                                " Ensure max of each phase < min of each other phase")
