# -*- coding: utf-8 -*-
"""
Description: A module for methods used commonly in model definition constructs.

Functions contained in this module:

- :func:`get_var`:Gets the variable value of the object
- :func:`set_var`:Sets variable of the object to a given value
- :func:`get_true_fields`:Resolves the args to pass to a dataobject given certain
  defaults
- :func:`get_true_field`:Gets the value that will be set to fieldname given *args and
  **kwargs
- :func:`is_iter`: Checks whether a data type should be interpreted as an iterable or
not.
- :func:`check_pickleability`:Checks to see which attributes of an object will pickle
  (and thus parallelize)"
- :func:`init_obj_attr`:Initializes attributes to a given object
- :func:`init_obj_dict`: Create a dict in an object for the attribute 'spec'.
- :func:`get_dataobj_track`:Gets tracking params for a given dataobject
  (State, Mode, Rand, etc)
- :func:`get_obj_track`:Gets tracking params for a given object (block, model, etc)
- :func:`t_key`:Used to generate keys for a given (float) time that is queryable as
  an attribute of an object/dict
- :func:`eq_units`:Provides conversion factor for from rateunit (str) to timeunit (str)

"""
from collections.abc import Iterable
import dill
import pickle
import time
from recordclass import asdict


def get_var(obj, var):
    """
    Gets the variable value of the object

    Parameters
    ----------
    var : str/list
        list specifying the attribute (or sub-attribute of the object
    Returns
    -------
    var_value: any
        value of the variable
    """
    if type(var) == str:
        var = var.split(".")
    if len(var) == 1:
        if type(obj) == dict:
            return obj[var[0]]
        else:
            return getattr(obj, var[0])
    else:
        if type(obj) == dict:
            return get_var(obj[var[0]], var[1:])
        else:
            return get_var(getattr(obj, var[0]), var[1:])


def set_var(obj, var, val):
    """
    Sets variable of the object to a given value

    Parameters
    ----------
    var : list/tuple of strings
        list of nested attributes
    val : attr
        attribute to set the value to

    Returns
    -------
    flowdict : dict
        dict of flows indexed by flownames
    """
    if type(var) == str:
        var = var.split(".")
    # if not attrgetter(".".join(var))(self):
    #    raise Exception("does not exist: "+str(var))

    if len(var) == 1:
        if type(obj) == dict:
            obj[var[0]] = val
        else:
            setattr(obj, var[0], val)
    else:
        if type(obj) == dict:
            set_var(obj[var[0]], var[1:], val)
        else:
            set_var(getattr(obj, var[0]), var[1:], val)


def get_true_fields(dataobject, *args, force_kwargs=False, **kwargs):
    """
    Resolves the args to pass to a dataobject given certain defaults, *args and **kwargs

    NOTE: must be used for pickling, since pickle passes arguments as *args and not
    **kwargs.
    """
    true_args = list(dataobject.__defaults__)
    for i, n in enumerate(dataobject.__fields__):
        if force_kwargs:
            true_args[i] = kwargs[n]
        if i < len(args):
            true_args[i] = args[i]
        elif n in kwargs:
            true_args[i] = kwargs[n]
    return true_args


def get_true_field(dataobject, fieldname, *args, **kwargs):
    """Gets the value that will be set to fieldname given *args and **kwargs"""
    if fieldname in kwargs:
        return kwargs[fieldname]
    field_ind = dataobject.__fields__.index(fieldname)
    if args and len(args) > field_ind:
        return args[field_ind]
    else:
        return dataobject.__defaults__[field_ind]


def is_iter(data):
    """
    Checks whether a data type should be interpreted as an iterable or not and returned
    as a single value or tuple/array
    """
    if isinstance(data, Iterable) and type(data) != str:
        return True
    else:
        return False


def check_pickleability(obj, verbose=True, try_pick=False, pause=0.2):
    """ Checks to see which attributes of an object will pickle (and parallelize)"""
    unpickleable = []
    try:
        itera = vars(obj)
    except:
        itera = {a: getattr(obj, a) for a in obj.__slots__}
    for name, attribute in itera.items():
        print(name)
        time.sleep(pause)
        try:
            if not dill.pickles(attribute):
                unpickleable = unpickleable + [name]
        except ValueError as e:
            raise ValueError("Problem in " + name +
                             " with attribute " + str(attribute)) from e
        if try_pick:
            try:
                a = pickle.dumps(attribute)
                b = pickle.loads(a)
            except:
                raise Exception(obj.name + " will not pickle")
    if try_pick:
        try:
            a = pickle.dumps(obj)
            b = pickle.loads(a)
        except:
            raise Exception(obj.name + " will not pickle")
    if verbose:
        if unpickleable:
            print("The following attributes will not pickle: " + str(unpickleable))
        else:
            print("The object is pickleable")
    return unpickleable


def init_obj_attr(obj, **attrs):
    """
    Initializes attributes to a given object, provided the object has a given
    _init_x in its class variables for the attribute x.

    Object is instantiated with the attribute x corresponding to the output of _init_x
    along with _args_x corresponding to the input dictionary given for x.

    Parameters
    ----------
    obj : object (Block/Flow/Model)
        Object to instantiate the attributes in
    **attrs : dict
        Dictionary arguments (or already instantiated objects) to use for the
        attributes.
    """
    for at in attrs:
        at_arg = attrs[at]
        if type(at_arg) != dict:
            at_arg = asdict(at_arg)
        setattr(obj, '_args_'+at, at_arg)
        init_at = getattr(obj, '_init_'+at)
        setattr(obj, at, init_at(**at_arg))


def init_obj_dict(obj, spec, name_end="s", set_attr=False):
    """
    Create a dict for the attribute 'spec'.

    Works by finding all attributes from the obj's parameter with the name 'spec' in
    them and adding them to the dict. Adds the dict to the object.

    Parameters
    ----------
    obj : object
        Object with _spec_ attributes
    spec : str
        Name of the attributes to initialize
    set_attr : bool
        Whether to also add the individual attributes attr to the obj
    sub_obj : str
        Sub-object to form the object from (e.g., 'p' if defined in a parameter).
        Default is '', which gets from obj.
    """
    spec_len = len(spec) + 1
    specs = {p[spec_len:]: obj.p[p] for p in obj.p.__fields__ if spec in p}
    specname = spec + name_end
    setattr(obj, specname, specs)
    if set_attr:
        for s_name in specs:
            setattr(obj, s_name, specs[s_name])


def get_dataobj_track(obj, track):
    """
    Gets tracking params for a given dataobject (State, Mode, Rand, etc)

    Parameters
    ----------
    obj : dataobject
        State/Mode/Rand. Requires .default_track class variable.
    track : track
        str/tuple. Attributes to track.
        'all' tracks all fields
        'default' tracks fields defined in default_track for the dataobject
        'none' tracks none of the fields

    Returns
    -------
    track : tuple
        fields to track
    """
    if not track or track == 'default':
        track = obj.default_track
    if track == 'all':
        track = obj.__fields__
    elif track == 'none':
        track = ()
    elif type(track) == str:
        track = (track,)
    return track


def get_obj_track(obj, track, all_possible=()):
    """
    Gets tracking params for a given object (block, model, etc)

    Parameters
    ----------
    obj : dataobject
        State/Mode/Rand. Requires .default_track class variable.
    track : track
        str/tuple. Attributes to track.
        'all' tracks all fields
        'default' tracks fields defined in default_track for the dataobject
        'none' tracks none of the fields

    Returns
    -------
    track : tuple
        fields to track
    """
    if track == 'default':
        track = obj.default_track
    if track == 'all':
        track = all_possible
    elif track in ['none', False]:
        track = ()
    elif type(track) == str:
        track = (track,)
    return track


def t_key(time):
    """Used to generate keys for a given (float) time that is queryable
    as an attribute of an object/dict, e.g. endresults.t10p0, the result at time
    t=10.0"""
    return 't'+'p'.join(str(time).split('.'))


def eq_units(rateunit, timeunit):
    """Provides conversion factor for from rateunit (str) to timeunit (str)
    Options for units are: 'sec', 'min', 'hr', 'day', 'wk', 'month', and 'year' """
    factors = {'sec': 1,
               'min': 60,
               'hr': 360,
               'day': 8640,
               'wk': 604800,
               'month': 2592000,
               'year': 31556952}
    return factors[timeunit]/factors[rateunit]


def get_obj_indicators(obj):
    """
    Gets the names of the indicators

    Parameters
    ----------
    obj : Simulable or Flow
        Object with indicators

    Returns
    -------
    indicators : dict
        dict of indicator names and their associated method handles.
    """
    indicators = {i[9:]: getattr(obj, i) for i in dir(obj) if i.startswith('indicate_')}
    return indicators


def return_true_indicators(obj, time):
    """
    Gets list of indicators

    Parameters
    ----------
    obj : flow/fxn/etc
        Object with an indicator
    time : float
        Time to execute the indicator method at.

    Returns
    -------
    list
        List of inticators that return true at time

    """
    return [f for f, ind in get_obj_indicators(obj).items() if ind(time)]
