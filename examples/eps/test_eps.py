# -*- coding: utf-8 -*-
"""
Created on Mon Dec 20 10:32:00 2021

@author: dhulse
"""
import unittest
from examples.eps.eps import EPS
from fmdtools.sim import propagate
import fmdtools.analyze as an
from fmdtools.sim.approach import SampleApproach
from fmdtools.define.common import check_pickleability
import numpy as np
import math
from tests.common import CommonTests


class epsTests(unittest.TestCase, CommonTests):
    def setUp(self):
        self.mdl = EPS()

    def test_backward_fault_prop_1(self):
        """Tests that defined fault cases that require reverse propagation propagate
        backwards through the graph as expected - distributor short leads to empty battery
        """
        endresults, mdlhist = propagate.one_fault(
            self.mdl, "distribute_ee", "short", desired_result="endfaults"
        )
        self.assertEqual(endresults["endfaults"]["store_ee"], ["no_storage"])

    def test_backward_fault_prop_2(self):
        """Tests that defined fault cases that require reverse propagation propagate
        backwards through the graph as expected - motor short leads to distributor short
        """
        endresults, mdlhist = propagate.one_fault(
            self.mdl, "ee_to_me", "short", desired_result="endfaults"
        )
        self.assertEqual(endresults["endfaults"]["store_ee"], ["no_storage"])
        self.assertEqual(endresults["endfaults"]["distribute_ee"], ["short"])

    def test_all_faults(self):
        """Some basic tests for propagating lists of faults in the model--
        that histories have length 1, endresults have >0 costs, and total costs are higher
        than repairs"""
        mdl = self.mdl
        endclasses, reshists = propagate.single_faults(mdl, showprogress=False)
        actual_num_faults = np.sum([len(f.m.faultmodes) for f in mdl.fxns.values()])
        self.assertEqual(len(endclasses.nest(1)), actual_num_faults + 1)
        hist_len_is_1 = all([len(v) == 1 for v in reshists.values()])
        self.assertTrue(hist_len_is_1)  # all histories have length 1
        all_have_costs = all(v > 0 for k, v in endclasses.get_values('.cost').items()
                             if 'nominal' not in k)
        self.assertTrue(all_have_costs)  # all endresults have positive costs
        repcosts = np.sum(
            [
                np.sum([m["rcost"] for m in f.m.faultmodes.values()])
                for f in mdl.fxns.values()
            ]
        )
        # fault costs higher than if it was just repairs
        total_simcosts = sum([v for v in endclasses.get_values('.cost').values()])
        self.assertGreater(total_simcosts, repcosts)

    def test_fault_app(self):
        """Tests that the expected number of scenarios are generated for a given
        approach"""
        actual_num_faults = int(
            np.sum([len(f.m.faultmodes) for f in self.mdl.fxns.values()])
        )
        for num_joint in [2, 3, actual_num_faults]:
            approach = SampleApproach(
                self.mdl,
                jointfaults={
                    "faults": num_joint,
                    "jointfuncs": True,
                    "pcond": 1.0,
                    "inclusive": False,
                },
            )
            self.assertEqual(
                len(approach.scenlist), math.comb(actual_num_faults, num_joint)
            )  # tests the length
            endclasses, reshists = propagate.approach(
                self.mdl, approach, showprogress=False
            )

    def test_pickleability(self):
        unpickleable = check_pickleability(self.mdl, verbose=False)
        self.assertTrue(unpickleable == [])

    def test_save_load_nominal(self):
        for extension in [".pkl", ".csv", ".json"]:
            self.check_save_load_onerun(
                self.mdl,
                "eps_mdlhist" + extension,
                "eps_endclass" + extension,
                "nominal",
            )

    def test_save_load_onefault(self):
        for extension in [".pkl", ".csv", ".json"]:
            self.check_save_load_onerun(
                self.mdl,
                "eps_mdlhist" + extension,
                "eps_endclass" + extension,
                "one_fault",
                faultscen=("store_ee", "no_storage", 0),
            )

    def test_save_load_multfault(self):
        for extension in [".pkl", ".csv", ".json"]:
            faultscen = {0: {"store_ee": ["no_storage"], "distribute_ee": "short"}}
            self.check_save_load_onerun(
                self.mdl,
                "eps_mdlhist" + extension,
                "eps_endclass" + extension,
                "sequence",
                faultscen=faultscen,
            )

    def test_save_load_singlefaults(self):
        self.check_save_load_singlefaults(
            self.mdl, "eps_mdlhists.pkl", "eps_endclasses.pkl"
        )
        self.check_save_load_singlefaults(
            self.mdl, "eps_mdlhists.csv", "eps_endclasses.csv"
        )
        self.check_save_load_singlefaults(
            self.mdl, "eps_mdlhists.json", "eps_endclasses.json"
        )

if __name__ == "__main__":
    unittest.main()

    mdl = EPS()

    approach = SampleApproach(mdl)

    # endresults, resgraph, mdlhist = propagate.one_fault(mdl, 'Distribute_EE', 'short')

    # mdl = EPS()
    # endresults, resgraph, mdlhist = propagate.one_fault(mdl, 'EE_to_ME', 'short')

    # mdl_nom = EPS()
    # endresults_nom, resgraph_nom, mdlhist_nom = propagate.nominal(mdl_nom)

    # endclasses, reshists = propagate.single_faults(mdl)
