"""
Description: Translates simulation outputs to pandas tables for display, export, etc.

Uses methods:
    - :meth:`fmea`:           Makes a simple fmea of the endclasses of a set of fault scenarios.
    - :meth:`result_summary_fmea`: Makes a table of endclass metrics, along with degraded functions/flows
    - :meth:`metricovertime`: Makes a table of the total metric, rate, and expected metric of all faults over time
    - :meth:`samptime`:       Makes a table of the times sampled for each phase given a dict (i.e. app.sampletimes)
    - :meth:`result_summary:`        Makes a table of a summary dictionary from a given model run
    - :meth:`nominal_stats`:  Makes a table of quantities of interest from endclasses from a nominal approach.
    - :meth:`nested_stats`:   Makes a table of quantities of interest from endclasses from a nested approach.
    - :meth:`nominal_factor_comparison`: Compares a metric for a given set of model parameters/factors over a set of nominal scenarios.
    - :meth:`nested_factor_comparison`: Compares a metric for a given set of model parameters/factors over a nested set of nominal and fault scenarios.
    - :meth:`label_faults`:Labels the faults
    - :meth:`dicttab`:Makes table of a generic dictionary
    - :meth:`maptab`:Makes table of a generic map


Legacy Functions:
-meth:`phasefmea`:(Use tabulate.fmea with option group_by='phase' instead) Makes a simple fmea of the endclasses of a set of fault scenarios run grouped by phase.
-meth:`summfmea`: (Use tabulate.fmea with group_by='fxnfault' instead.) Makes a simple fmea of the endclasses of a set of fault scenarios run grouped by fault.
    
"""
# File Name: analyze/tabulate.py
# Author: Daniel Hulse
# Created: November 2019 (Refactored April 2020)

import pandas as pd
import numpy as np
from fmdtools.analyze.result import nan_to_x, Result, bootstrap_confidence_interval


def label_faults(faulthist, df, fxnlab, labels):
    if type(faulthist) == dict:
        for fault in faulthist:
            label = (fxnlab, fault+' fault')
            labels+=[label]
            df[label] = faulthist[fault]
    elif len(faulthist) == 1:
        label = (fxnlab, 'faults')
        labels+=[label]
        df[label] = faulthist


def metricovertime(endclasses, app, metric='cost'):
    """
    Makes a table of the total metric, rate, and expected metric of all faults over time

    Parameters
    ----------
    endclasses : dict
        dict with rate, metric, and expected metric values for each injected scenario
    app : sampleapproach
        sample approach used to generate the list of scenarios
    metric : str
        metric from dict to tabulate over time. Default is 'cost'
    Returns
    -------
    met_overtime : dataframe
        pandas dataframe with the total metric, rate, and expected metric for the set of scenarios
    """
    expected_metric = "expected "+metric
    met_overtime = {metric:{time:0.0 for time in app.times}, 'rate':{time:0.0 for time in app.times}, expected_metric:{time:0.0 for time in app.times}}
    for scen in app.scenlist:
        met_overtime[metric][scen.time]+=endclasses[scen.name][metric]
        met_overtime['rate'][scen.time]+=endclasses[scen.name]['rate']
        met_overtime[expected_metric][scen.time]+=endclasses[scen.name][expected_metric] 
    return pd.DataFrame.from_dict(met_overtime)


def samptime(sampletimes):
    """Makes a table of the times sampled for each phase given a dict (i.e. app.sampletimes)"""
    table = pd.DataFrame()
    for phase, times in sampletimes.items():
        table[phase] = [str(list(times.keys()))]
    return table.transpose() 


def result_summary(endresult, mdlhist, *attrs):
    """
    Makes a table of results (degraded functions/flows, classification) of a single run

    Parameters
    ----------
    endresult : Result
        Result with end-state classification
    mdlhist : History
        History 
    *attrs : str
        Names of attributes to check in the history for degradation/faulty.

    Returns
    -------
    table : pd.DataFrame
        Table with summary
    """
    hist_summary = mdlhist.get_fault_degradation_summary(*attrs)
    if 'endclass' in endresult:
        endresult = endresult['endclass']
    table = pd.DataFrame(endresult.data, index=[0])
    table['degraded'] = [hist_summary.degraded]
    table['faulty'] = [hist_summary.faulty]
    return table


def dicttab(dictionary):
    """Makes table of a generic dictionary"""
    return pd.DataFrame(dictionary, index=[0])


def maptab(mapping):
    """Makes table of a generic map"""
    table = pd.DataFrame(mapping)
    return table.transpose()


def nominal_stats(nomapp, nomapp_endclasses, metrics='all', inputparams='from_range', scenarios='all'):
    """
    Makes a table of quantities of interest from endclasses.

    Parameters
    ----------
    nomapp : NominalApproach
        NominalApproach used to generate the simulation.
    nomapp_endclasses: dict
        End-state classifcations for the set of simulations from propagate.nominalapproach()
    metrics : 'all'/list, optional
        Metrics to show on the plot. The default is 'all'.
    inputparams : 'from_range'/'all',list, optional
        Parameters to show on the plot. The default is 'from_range'.
    scenarios : 'all','range'/list, optional
        Scenarios to include in the plot. 'range' is a given range_id in the nominalapproach.
    Returns
    -------
    table : pandas DataFrame
        Table with the metrics of interest layed out over the input parameters for the set of scenarios in endclasses
    """
    if metrics == 'all':
        metrics = [*nomapp_endclasses[[*nomapp_endclasses][0]]]
    if scenarios == 'all':
        scens = [*nomapp_endclasses]
    elif type(scenarios) == str:
        scens = nomapp.ranges[scenarios]['scenarios']
    elif not type(scenarios) == list:
        raise Exception("Invalid option for scenarios. Provide 'all'/'rangeid' or list")
    else:
        scens = scenarios
    if inputparams == 'from_range':
        ranges = [*nomapp.ranges]
        if not(scenarios == 'all') and not(type(scenarios) == list):
            app_range = scenarios
        elif len(ranges) == 1:
            app_range = ranges[0]
        else:
            raise Exception("Multiple approach ranges "+str(ranges)+" in approach. Use inputparams=`all` or inputparams=[param1, param2,...]")
        inputparams = [*nomapp.ranges[app_range]['inputranges']]
    elif inputparams == 'all':
        inputparams = [*nomapp.scenarios.values()][0].inputparams
    elif inputparams == 'none':
        inputparams = []
    table_values = []
    for inputparam in inputparams:
        table_values.append([nomapp.scenarios[e].inputparams[inputparam] for e in scens])
    for metric in metrics:
        table_values.append([nomapp_endclasses[e][metric] for e in scens])
    table = pd.DataFrame(table_values, columns=[*nomapp_endclasses], index=inputparams+metrics)
    return table


def nominal_factor_comparison(nomapp, endclasses, params, metrics='all', rangeid='default', nan_as=np.nan, percent=True,  give_ci=False, **kwargs):
    """
    Compares a metric for a given set of model parameters/factors over set of nominal scenarios.

    Parameters
    ----------
    nomapp : NominalApproach
        Nominal Approach used to generate the simulations
    endclasses : dict
        dict of endclasses from propagate.nominal_approach or nested_approach with structure: 
            {scen_x:{metric1:x, metric2:x...}} or {scen_x:{fault:{metric1:x, metric2:x...}}} 
    params : list/str
        List of parameters (or parameter) to use for the factor levels in the comparison
    metrics : 'all'/list, optional
        Metrics to show in the table. The default is 'all'.
    rangeid : str, optional
        Nominal Approach range to use for the test, if run over a single range.
        The default is 'default', which either:
            - picks the only range (if there is only one), or
            - compares between ranges (if more than one)
    nan_as : float, optional
        Number to parse NaNs as (if present). The default is np.nan.
    percent : bool, optional
        Whether to compare metrics as bools (True - results in a comparison of percentages of indicator variables) 
        or as averages (False - results in a comparison of average values of real valued variables). The default is True.
    give_ci = bool:
        gives the bootstrap confidence interval for the given statistic using the given kwargs
        'combined' combines the values as a strings in the table (for display)
    give_ci : bool
        ....
    kwargs : keyword arguments for bootstrap_confidence_interval (sample_size, num_samples, interval, seed)
    Returns
    -------
    table : pandas table
        Table with the metric statistic (percent or average) over the nominal scenario and each listed function/mode (as differences or averages)
    """
    if rangeid == 'default':
        if len(nomapp.ranges.keys()) == 1:
            rangeid = [*nomapp.ranges.keys()][0]
            factors = nomapp.get_param_scens(rangeid, *params)
        else:
            factors = {rangeid:nomapp.ranges[rangeid]['scenarios'] for rangeid in nomapp.ranges}
    else:
        factors = nomapp.get_param_scens(rangeid, *params)
    if [*endclasses.values()][0].get('nominal', False):
        endclasses = {scen:ec['nominal'] for scen, ec in endclasses.items()}
    if metrics == 'all':
        metrics = [ec for ec, val in [*endclasses.values()][0].items() if type(val) in [float, int]]
    
    if type(params) == str:
        params = [params]
    full_stats = []
    for metric in metrics:
        factor_stats = []
        for factor, scens in factors.items():
            endclass_fact = {scen:endclass for scen, endclass in endclasses.items() if scen in scens}

            if not percent:
                nominal_metrics = [nan_to_x(scen[metric], nan_as) for scen in endclass_fact.values()]
            else:
                nominal_metrics = [np.sign(float(nan_to_x(scen[metric], nan_as))) for scen in endclass_fact.values()]
            factor_stats = factor_stats + [sum(nominal_metrics)/len(nominal_metrics)]
            if give_ci: 
                factor_boot, factor_lb, factor_ub = bootstrap_confidence_interval(nominal_metrics, **kwargs)
                factor_stats = factor_stats + [factor_lb, factor_ub]
        full_stats.append(factor_stats)
    if give_ci == 'combined':
        full_stats = [[str(round(v, 3))+' ('+str(round(f[i+1], 3))+','+str(round(f[i+2], 3))+')' for i, v in enumerate(f) if not i%3] for f in full_stats]
    if not give_ci:
        table = pd.DataFrame(full_stats, columns=factors, index=metrics)
        table.columns.name = tuple(params)
    else:           
        columns = [(f, stat) for f in factors for stat in ["", "LB", "UB"]]
        table = pd.DataFrame(full_stats, columns=columns, index=metrics)
        table.columns = pd.MultiIndex.from_tuples(table.columns, names=['metric', ''])
        table.columns.name = tuple(params)
    return table


def nested_factor_comparison(nomapp, nested_endclasses, params, value, faults='functions', rangeid='default', nan_as=np.nan, percent=True, difference=True, give_ci=False, **kwargs):
    """
    Compares a metric for a given set of model parameters/factors over a nested set of nominal and fault scenarios.

    Parameters
    ----------
    nomapp : NominalApproach
        Nominal Approach used to generate the simulations
    nested_endclasses : dict
        dict of endclasses from propagate.nested_approach with structure: {scen_x:{fault:{metric1:x, metric2:x...}}}
    params : list/str
        List of parameters (or parameter) to use for the factor levels in the comparison
    value : string
        metric of the endclass (returned by mdl.find_classification) to use for the comparison.
    faults : str/list, optional
        Set of faults to run the comparison over
            --'modes' (all fault modes),
            --'functions' (modes for each function are grouped)
            --'mode type' (modes with the same name are grouped)
            -- or a set of specific modes/functions. The default is 'functions'.
            -- or a tuple of form (group_by, apps, *arg), where
                - group_by is an argument to SampleApproach.get_scenid_groups
                - apps is a dictionary of approaches corresponding to the endclasses (from prop.nested_approach)
                - arg is:
                    - when using 'fxnclassfault' and 'fxnclass' options: a model
                    - when using 'modetype' options: a dictionary grouping modes by type
    rangeid : str, optional
        Nominal Approach range to use for the test, if run over a single range.
        The default is 'default', which either:
            - picks the only range (if there is only one), or
            - compares between ranges (if more than one)
    nan_as : float, optional
        Number to parse NaNs as (if present). The default is np.nan.
    percent : bool, optional
        Whether to compare metrics as bools (True - results in a comparison of percentages of indicator variables) 
        or as averages (False - results in a comparison of average values of real valued variables). The default is True.
    difference : bool, optional
        Whether to tabulate the difference of the metric from the nominal over each scenario (True),
        or the value of the metric over all (False). The default is True.
    give_ci = bool:
        gives the bootstrap confidence interval for the given statistic using the given kwargs
        'combined' combines the values as a strings in the table (for display)
    kwargs : keyword arguments for bootstrap_confidence_interval (sample_size, num_samples, interval, seed)
    Returns
    -------
    table : pandas table
        Table with the metric statistic (percent or average) over the nominal scenario and each listed function/mode (as differences or averages)
    """
    nested_endclasses=nested_endclasses.nest()
    if rangeid == 'default':
        if len(nomapp.ranges.keys()) == 1:
            rangeid = [*nomapp.ranges.keys()][0]
            factors = nomapp.get_param_scens(rangeid, *params)
        else:
            factors = {rangeid:nomapp.ranges[rangeid]['scenarios'] for rangeid in nomapp.ranges}
    else:
        factors = nomapp.get_param_scens(rangeid, *params)
    if faults == 'functions':
        faultlist = set(["_".join(e.split("_")[:-2]) for scen in nested_endclasses.nest() 
                         for e in nested_endclasses.get(scen).nest()])
    elif faults == 'modes':
        faultlist = set(["_".join(e.split("_")[:-1]) for scen in nested_endclasses.nest()
                         for e in nested_endclasses.get(scen).nest()])
    elif faults == 'mode type':
        faultlist = set(["_".join(e.split("_")[-1]) for scen in nested_endclasses.nest()
                         for e in nested_endclasses.get(scen).nest()])
    elif type(faults) == str:
        raise Exception("Invalid faults option: "+faults)
    elif type(faults) == list:
        faultlist = set(faults)
    elif type(faults) == tuple:
        group_by=faults[0]; apps=faults[1]; group_dict={}
        if group_by in ['fxnclassfault','fxnclass']: 
            mdl = faults[2]
            group_dict = {cl:mdl.fxns_of_class(cl) for cl in mdl.fxnclasses()}
        elif group_by == 'modetype':
            group_dict=faults[2]
        fault_scen_groups = {factor:{scen:apps[scen].get_scenid_groups(group_by, group_dict) for scen in scens} for factor, scens in factors.items()}
        faultlist = {fsname:set() for dicts in fault_scen_groups.values() for group in dicts.values() for fsname in group}
    else:
        faultlist = faults
    if type(faults) == tuple:
        faultlist.pop('nominal', 'nothing')
    else:
        faultlist.discard('nominal'); faultlist.discard(' '); faultlist.discard('')
    if type(params) == str:
        params=[params]
    full_stats=[]
    for factor, scens in factors.items():
        endclass_fact = Result({scen:endclass for scen, endclass in nested_endclasses.items() if scen in scens})
        ec_metrics = endclass_fact.overall_diff(value, nan_as=nan_as, as_ind=percent, no_diff=not difference)

        if not percent: 
            nominal_metrics = [nan_to_x(res_scens['nominal'].endclass[value], nan_as) for res_scens in endclass_fact.values()]
        else:           
            nominal_metrics = [np.sign(float(nan_to_x(nan_to_x(res_scens.endclass['nominal'][value]), nan_as))) for res_scens in endclass_fact.values()]
        factor_stats=[sum(nominal_metrics)/len(nominal_metrics)]
        if give_ci: 
            factor_boot, factor_lb, factor_ub = bootstrap_confidence_interval(nominal_metrics, **kwargs)
            factor_stats = factor_stats + [factor_lb, factor_ub]
        if type(faults)==tuple:
            faultlist = {f:set() for f in faultlist}
            for scen, groups in fault_scen_groups[factor].items():
                for group, faultscens in groups.items():
                    if not faultlist.get(group, False) and faultscens:  faultlist[group]=set(faultscens)
                    else:                                               faultlist[group].update(faultscens)
                faultlist.pop('nominal', 'nothing')
        for fault in faultlist:
            if type(faults)==tuple:     fault_metrics=[metric for res_scens in ec_metrics.values() for res_scen,metric in res_scens.items() if res_scen in faultlist[fault]]
            elif faults=='functions':     fault_metrics = [metric for res_scens in ec_metrics.values() for res_scen,metric in res_scens.items() if fault in res_scen.partition(' ')[0]]
            else:                       fault_metrics = [metric for res_scens in ec_metrics.values() for res_scen,metric in res_scens.items() if fault in res_scen.partition(',')[0]]
            if len(fault_metrics)>0:    
                factor_stats.append(sum(fault_metrics)/len(fault_metrics))
                if give_ci: 
                    factor_boot, factor_lb, factor_ub = bootstrap_confidence_interval(fault_metrics, **kwargs)
                    factor_stats= factor_stats+[factor_lb, factor_ub]
            else:                       
                if not give_ci:
                    factor_stats.append(np.NaN)
                else:
                    factor_stats= factor_stats + [np.NaN,np.NaN,np.NaN]
        full_stats.append(factor_stats)
    if give_ci=='combined': full_stats = [[str(round(v,3))+' ('+str(round(f[i+1],3))+','+str(round(f[i+2],3))+')' for i,v in enumerate(f) if not i%3] for f in full_stats]
    if give_ci !=True: 
        table = pd.DataFrame(full_stats, columns = ['nominal']+list(faultlist), index=factors)
        table.columns.name=tuple(params)
    else:           
        columns = [(f, stat) for f in ['nominal']+list(faultlist) for stat in ["", "LB", "UB"]]
        table = pd.DataFrame(full_stats, columns=columns, index=factors)
        table.columns = pd.MultiIndex.from_tuples(table.columns, names=['fault', ''])
        table.columns.name=tuple(params)
    return table

def nested_stats(nomapp, nested_endclasses, percent_metrics=[], rate_metrics=[], average_metrics=[], expected_metrics=[], inputparams='from_range', scenarios='all'):
    """
    Makes a table of quantities of interest from endclasses.

    Parameters
    ----------
    nomapp : NominalApproach
        NominalApproach used to generate the simulation.
    endclasses : Result
        End-state classifcations for the set of simulations from propagate.nested_approach()
    percent_metrics : list
        List of metrics to calculate a percent of (e.g. use with an indicator variable like failure=1/0 or True/False)
    rate_metrics : list
        List of metrics to calculate the probability of using the rate variable in endclasses
    average_metrics : list
        List of metrics to calculate an average of (e.g., use for float values like speed=25)
    expected_metrics : list
        List of metrics to calculate the expected value of using the rate variable in endclasses
    inputparams : 'from_range'/'all',list, optional
        Parameters to show on the table. The default is 'from_range'.
    scenarios : 'all','range'/list, optional
        Scenarios to include in the table. 'range' is a given range_id in the nominalapproach.
    Returns
    -------
    table : pandas DataFrame
        Table with the averages/percentages of interest layed out over the input parameters for the set of scenarios in endclasses
    """
    if scenarios=='all':            scens = [k.split('.')[0] for k in nested_endclasses]
    elif type(scenarios)==str:      scens = nomapp.ranges[scenarios]['scenarios']
    elif not type(scenarios)==list: raise Exception("Invalid option for scenarios. Provide 'all'/'rangeid' or list")
    else:                           scens = scenarios
    if inputparams=='from_range': 
        ranges=[*nomapp.ranges]
        if not(scenarios=='all') and not(type(scenarios)==list):    app_range= scenarios
        elif len(ranges)==1:                                        app_range=ranges[0]
        else: raise Exception("Multiple approach ranges "+str(ranges)+" in approach. Use inputparams=`all` or inputparams=[param1, param2,...]")
        inputparams= [*nomapp.ranges[app_range]['p']]
    elif inputparams=='all':
        inputparams=[*nomapp.scenarios.values()][0].p
    table_values=[]; table_rows = inputparams
    for inputparam in inputparams:
        table_values.append([nomapp.scenarios[e].p[inputparam] for e in scens])
    for metric in percent_metrics:  
        table_values.append([nested_endclasses.get(e).percent(metric) for e in scens])
        table_rows.append('perc_'+metric)
    for metric in rate_metrics:     
        table_values.append([nested_endclasses.get(e).rate(metric) for e in scens])
        table_rows.append('rate_'+metric)
    for metric in average_metrics:  
        table_values.append([nested_endclasses.get(e).average(metric) for e in scens])
        table_rows.append('ave_'+metric)
    for metric in expected_metrics: 
        table_values.append([nested_endclasses.get(e).expected(metric) for e in scens])
        table_rows.append('exp_'+metric)
    table = pd.DataFrame(table_values, columns=[*nested_endclasses], index=table_rows)
    return table

##FMEA-like tables
def result_summary_fmea(endresult, mdlhist, *attrs, metrics=()):
    """
    Makes full fmea table (degraded functions/flows, all metrics in endclasses) 
    of scenarios given endclasses dict and summaries dict (degraded functions, degraded flows)

    Parameters
    ----------
    endresult : Result
        Result (over scenarios) to get metrics from
    mdlhist : History
        History (over scenarios) to get degradations/faults from
    *attrs : strs
        Model constructs to check if faulty/degraded.
    metrics : tuple, optional
        Metrics to include from endresult. The default is ().

    Returns
    -------
    pandas.DataFrame
        Table of metrics and degraded functions/flows over scenarios
    """
    from fmdtools.analyze.result import History
    deg_summaries={}; fault_summaries={}
    mdlhist = mdlhist.nest(levels=1)
    for scen, hist in mdlhist.items():
        hist_comp = History(faulty=hist, nominal=mdlhist.nominal)
        hist_summary = hist_comp.get_fault_degradation_summary(*attrs)
        deg_summaries[scen] = str(hist_summary.degraded)
        fault_summaries[scen] = str(hist_summary.faulty)
    degradedtable = pd.DataFrame(deg_summaries, index=['degraded'])
    faulttable = pd.DataFrame(fault_summaries, index=['faulty'])
    simplefmea=endresult.create_simple_fmea(*metrics)
    fulltable = pd.concat([degradedtable, faulttable, simplefmea.transpose()])
    return fulltable.transpose()

def fmea(endclasses, app, metrics=[], weight_metrics=[], avg_metrics = [], perc_metrics=[],
         mult_metrics={}, extra_classes={}, group_by='none', sort_by=False, mdl={}, mode_types={}, ascending=False, empty_as=0.0):
    """
    Makes a user-definable fmea of the endclasses of a set of fault scenarios.

    Parameters
    ----------
    endclasses : dict
        dict of endclasses of the simulation runs
    app : sampleapproach
        sample approach used for the underlying probability model of the set of scenarios run
    metrics : list
        generic unweighted metrics to query. The default is []. 'all' presents all metrics.
        metrics are summed over grouped scenarios.
    weight_metrics: list
        weighted metrics to query. The default is ['rate']. 
        metrics are weighted according to the number in each phase and then averaged
    avg_metrics: list
        metrics to average and query. The default is ['cost']. 
        avg_metrics are averaged over groups, rather than a total.
    perc_metrics : list, optional
        metrics to treat as indicator variables to calculate a percentage. The default is [].
        perc_metrics are treated as indicator variables and averaged over groups.
    mult_metrics : dict, optional
        mult_metrics are new metrics calculated by multiplying existing metrics 
        (e.g., to calculate expectations or risk values like an expected cost or RPN)
        The default is {"expected cost":['rate', 'cost']}.
    extra_classes : dict, optional
        An additional set of endclasses to include in the table (e.g., summaries from process.hists). 
        The default is {}.
    group_by : str, optional
        Way of grouping fmea rows. The default is 'none'.
        - 'none':           All scenarios are displayed individually
        - 'phase':          All identical scenarios (fxn, mode) within a given phase are grouped 
        - 'fxnfault':       All identical scenarios (fxn, mode) are grouped
        - 'mode':           All scenarios with the same mode name are grouped
        - 'modetype':      All scenarios with the same mode type, where mode types are strings in the mode name. Mode types must be given.
        - 'functions':      All scenarios and modes from a given function are grouped.
        - 'times':          All scenarios and modes at a given time are grouped
        - 'fxnclassfault':  All scenarios (fxnclass, mode) from a given function class are grouped. A Model must be provided.
        - 'fxnclass':       All scenarios from a given function class are grouped. A Model must be provided.
    mode_types : set
        Mode types to group by in 'mode type' option
    mdl : Model
        Model for use in 'fxnclassfault' and 'fxnclass' options
    sort_by : str, optional
        Column value to sort the table by. The default is "expected cost".
    ascending : bool, optional
        Whether to sort in ascending order. The default is False.
    empty_as : float/'nan'
        How to calculate stats of empty variables (for avg_metrics). Default is 0.0.

    Returns
    -------
    fmea_table : DataFrame
        pandas table with given metrics grouped as
    """
    group_dict = {}
    if group_by in ['fxnclassfault','fxnclass']:
        if not mdl:
            raise Exception("No model mdl provided.")
        group_dict = {cl: mdl.fxns_of_class(cl) for cl in mdl.fxnclasses()}
    elif group_by == 'modetype':
        group_dict = mode_types
    grouped_scens = app.get_scenid_groups(group_by, group_dict)

    if type(metrics) == str:
        metrics = [metrics]
    if type(weight_metrics) == str:
        weight_metrics = [weight_metrics]
    if type(perc_metrics) == str:
        perc_metrics = [perc_metrics]
    if type(avg_metrics) == str:
        avg_metrics = [avg_metrics]

    if not metrics and not weight_metrics and not perc_metrics and not avg_metrics and not mult_metrics:
        # default fmea is a cost-based table
        weight_metrics = ["rate"]
        avg_metrics = ["cost"]
        mult_metrics = {"expected cost": ['rate', 'cost']}

    endclasses.update(extra_classes)

    id_weights = app.get_id_weights()
    id_weights['nominal'] = 1.0

    allmetrics = metrics+weight_metrics+avg_metrics+perc_metrics+[*mult_metrics.keys()]

    if not sort_by:
        if "expected cost" in mult_metrics:
            sort_by = "expected_cost"
        else:
            sort_by = allmetrics[-1]

    fmeadict = {g: dict.fromkeys(allmetrics) for g in grouped_scens}
    for group, ids in grouped_scens.items():
        for metric in metrics:
            fmeadict[group][metric] = sum([endclasses.get(scenid).get('endclass.'+metric) for scenid in ids])
        for metric in weight_metrics:
            fmeadict[group][metric] = sum([endclasses.get(scenid).get('endclass.'+metric)*id_weights[scenid] for scenid in ids])
        for metric in perc_metrics:
            fmeadict[group][metric] = Result({scenid: endclasses.get(scenid) for scenid in ids}).percent(metric)
        for metric in avg_metrics:    
            fmeadict[group][metric] = Result({scenid: endclasses.get(scenid) for scenid in ids}).average(metric, empty_as=empty_as)
        for metric, to_mult in mult_metrics.items():
            if set(to_mult).intersection(weight_metrics):
                fmeadict[group][metric] = sum([np.prod([endclasses.get(scenid).get('endclass.'+m) 
                                                        for m in to_mult])*id_weights[scenid] for scenid in ids])
            else:
                fmeadict[group][metric] = sum([np.prod([endclasses.get(scenid).get('endclass.'+m) 
                                                        for m in to_mult]) for scenid in ids])

    table = pd.DataFrame(fmeadict)
    table = table.transpose()
    if sort_by not in allmetrics:
        sort_by = allmetrics[0]
    table = table.sort_values(sort_by, ascending=ascending)
    return table

    
def phasefmea(endclasses, app, metrics=["rate", "expected cost"], weight_metrics=["cost"], sort_by=None, ascending=False):
    """
    (LEGACY FUNCTION) Makes a simple fmea of the endclasses of a set of fault scenarios run grouped by phase.
    Use tabulate.fmea with option group_by='phase' instead.

    Parameters
    ----------
    endclasses : dict
        dict of endclasses of the simulation runs
    app : sampleapproach
        sample approach used for the underlying probability model of the set of scenarios run
    metrics : list
        unweighted metrics to query. The default is ['rate', 'expected cost']
    weight_metrics: list
        weighted metrics to query. The default is ['cost']. 
        Weights are used to calculate an average, rather than a total.
    sort_by : str
        metric to stort the table by. default is 'expected cost'
    ascending : bool
        whether to sort ascending. Default is False.
    Returns
    -------
    tab: dataframe
        table with metrics of each fault in each phase
    """
    tab = fmea(endclasses, app, group_by='phase', metrics=metrics, weight_metrics=weight_metrics, sort_by=sort_by, ascending=ascending)
    return tab
    

def summfmea(endclasses, app, metrics=["rate", "expected cost"], weight_metrics=["cost"], sort_by=None, ascending=False):
    """
    (LEGACY FUNCTION) Makes a simple fmea of the endclasses of a set of fault scenarios run grouped by fault.
    Use tabulate.fmea with group_by='fxnfault' instead.
    
    Parameters
    ----------
    endclasses : dict
        dict of endclasses of the simulation runs
    app : sampleapproach
        sample approach used for the underlying probability model of the set of scenarios run
    metrics : list
        unweighted metrics to query. The default is ['rate', 'expected cost']
    weight_metrics : list
        ..
    sort_by : str
        metric to stort the table by. default is 'expected cost'
    ascending : bool
        whether to sort ascending. Default is False
    Returns
    -------
    tab: dataframe
        table with metrics of each fault (over all phases)
    """
    tab = fmea(endclasses, app, group_by='fxnfault', metrics=metrics, weight_metrics=weight_metrics, sort_by=sort_by, ascending=ascending)
    return tab
