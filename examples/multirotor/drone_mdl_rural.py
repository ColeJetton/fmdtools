# -*- coding: utf-8 -*-
"""
File name: quad_mdl.py
Author: Daniel Hulse
Created: June 2019, revised Nov 2022
Description: A fault model of a multi-rotor drone.
"""
import numpy as np
from fmdtools.define.parameter import Parameter
from fmdtools.define.state import State
from fmdtools.define.mode import Mode
from fmdtools.define.block import FxnBlock, Component, CompArch
from fmdtools.define.flow import Flow
from fmdtools.define.model import Model
from fmdtools.sim.approach import SampleApproach
from fmdtools.analyze.result import History

from examples.multirotor.drone_mdl_static import EE, Force, Control, DesTraj, DOFs
from examples.multirotor.drone_mdl_static import DistEE, StoreEEState
from drone_mdl_static import CtlDOF as CtlDOFStat

from examples.multirotor.drone_mdl_dynamic import DroneEnvironmentGridParam
from examples.multirotor.drone_mdl_dynamic import DroneEnvironment, ViewEnvironment
from drone_mdl_dynamic import PlanPathState as PlanPathStateDyn
from drone_mdl_dynamic import PlanPath as PlanPathDyn
from drone_mdl_dynamic import HoldPayload as HoldPayloadDyn

from drone_mdl_hierarchical import AffectDOF as AffectDOFHierarchical

from recordclass import asdict

# DEFINE PARAMETERS


class ResPolicy(Parameter, readonly=True):
    """
    Define the resilience policy/contingency management of the drone.

    Fields
    -------
    bat : str
        Where to go if a battery fault is detected.
    line : str
        Where to go if a lien fault is detected.
    """

    bat: str = 'to_home'
    bat_set = ('to_nearest', 'to_home', 'emland', 'land', 'move', 'continue')
    line: str = 'emland'
    line_set = ('to_nearest', 'to_home', 'emland', 'land', 'move', 'continue')


class DronePhysicalParameters(Parameter, readonly=True):
    """
    Define the physical characteristics of the drone based on architectures.

    Fields (input)
    -------
    bat : str
        Battery cell architecture.
    linearch : str
        Line/rotor architecture.

    Fields (calculated)
    -------
    batweight : float
        Total battery weight
    archweight : float
        Total line architecture weight
    archdrag : float
        Total line architecture drag
    """

    bat: str = 'monolithic'
    bat_set = ('monolithic', 'series-split', 'parallel-split', 'split-both')
    linearch: str = 'quad'
    linearch_set = ('quad', 'hex', 'oct')
    batweight: float = 0.4
    archweight: float = 1.2
    archdrag: float = 0.95
    def __init__(self, *args, **kwargs):
        args = self.get_true_fields(*args, **kwargs)
        args[2] = {'monolithic': 0.4, 'series-split': 0.5,
                   'parallel-split': 0.5, 'split-both': 0.6}[args[0]]
        args[3] = {'quad': 1.2, 'hex': 1.6, 'oct': 2.0}[args[1]]
        args[4] = {'quad': 0.95, 'hex': 0.85, 'oct': 0.75}[args[1]]
        super().__init__(*args)


class DroneParam(Parameter, readonly=True):
    """
    Overall parameters for the rural Drone model.

    Fields
    -------
    respolicy: ResPolicy
    flighplan: tuple
        sequence of locations for the drone to fly through
    env_param: DroneEnvironmentGridParam
    phys_param: DronePhysicalParameters
    """

    respolicy:  ResPolicy = ResPolicy()
    flightplan: tuple = ((0, 0, 0),  # flies through a few points and back to the start
                         (0, 0, 100),
                         (100, 0, 100),
                         (100, 100, 100),
                         (150, 150, 100),
                         (0, 0, 100),
                         (0, 0, 0))
    env_param: DroneEnvironmentGridParam = DroneEnvironmentGridParam()
    phys_param: DronePhysicalParameters = DronePhysicalParameters()


# DEFINE FLOWS
class HSigState(State):
    """State defining health signals (hstate: nominal/faulty)."""

    hstate: str = 'nominal'


class HSig(Flow):
    """Health signal flow."""

    _init_s = HSigState


class RSigState(State):
    """State defining Recovery signal (mode: continue, to_home, etc)."""

    mode: str = 'continue'


class RSig(Flow):
    """Recovery signal flow."""

    _init_s = RSigState

# DEFINE FUNCTIONS


class BatState(State):
    """
    Battery States.

    Fields
    -------
    soc: float
        State of charge, with values (0-100)
    e_t: float
        Power transference with nominal value 1.0
    """

    soc:  float = 100.0
    ee_e: float = 1.0
    e_t:  float = 1.0


class BatMode(Mode):
    """
    Battery Modes.

    Modes
    -------
    short: Fault
        inability to transfer power
    degr: Fault
        less power tranferrence
    break: Fault
        inability to transfer power
    nocharge: Fault
        zero state of charge (need a way to trigger these modes)
    lowcharge: Fault
        state of charge of 20
    """

    failrate = 1e-4
    faultparams = {'short': (0.2, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 100),
                   'degr': (0.2, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 100),
                   'break': (0.2, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 100),
                   'nocharge': (0.6, {"taxi": 0.7, "move": 0.2, "land": 0.1}, 100),
                   'lowcharge': (0.4, {"taxi": 0.5, "move": 0.2, "land": 0.3}, 100)}
    key_phases_by = 'plan_path'


class BatParam(Parameter):
    """
    Individual battery properties.

    Fields (input)
    -------
    weight: float
        Drone weight.
    drag: float
        Drone drag.
    series: int
        Number of packs in series.
    parallel : int
        Number of packs in parallel.
    voltage : float
        Pack voltage.

    Fields (calculated)
    -------
    avail_eff : float
        Available effort (voltage).
    maxa : float
        Maximum current.
    amt : float
        Energy stored (in flight time).
    """

    avail_eff: float = 0.0
    maxa: float = 0.0
    amt: float = 0.0
    weight: float = 0.1
    drag: float = 0.95
    series: int = 1
    parallel: int = 1
    voltage: float = 12.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.avail_eff = 1/self.parallel
        self.maxa = 2/self.series
        self.amt = 4200/60 * (self.drag/self.weight)


class Battery(Component):
    """Battery component used to hold energy in distributed architecture."""

    _init_s = BatState
    _init_m = BatMode
    _init_p = BatParam

    def behavior(self, fs, ee_outr, time):
        """Battery behavior returning electrical transference, soc, and fault state."""
        # If current is too high, battery breaks.
        if fs < 1.0 or ee_outr > self.p.maxa:
            self.m.add_fault('break')

        # Determine transference state based on faults
        if self.m.has_fault('short'):
            self.s.e_t = 0.0
        elif self.m.has_fault('break'):
            self.s.e_t = 0.0
        elif self.m.has_fault('degr'):
            self.s.e_t = 0.5*self.p.avail_eff
        else:
            self.s.e_t = self.p.avail_eff

        # Increment power use/soc (once per timestep)
        if time > self.t.time:
            self.s.inc(soc=-100*ee_outr*self.p.parallel *
                       self.p.series*(time-self.t.time)/self.p.amt)
            self.t.time = time

        # Calculate charge modes/values
        if self.s.soc < 20:
            self.m.add_fault('lowcharge')
        if self.s.soc < 1:
            self.m.replace_fault('lowcharge', 'nocharge')
            self.s.put(soc=0.0, e_t=0.0)
            er_res = ee_outr
        else:
            er_res = 0.0
        return self.s.e_t, self.s.soc, er_res


class BatArch(CompArch):
    """
    Battery architecture.

    Defined by archtype parameter with options:
        - 'monolythic':
            Single Battery
        - 'series-split':
            Two batteries put in series
        - 'parallel-split':
            two batteries put in parallel
        - 'split-both':
            four batteries arranged in a series-parallel configuration
    """

    archtype: str = 'monolithic'
    batparams: dict = {}  # weight, cap, voltage, drag_factor
    weight: float = 0.0
    drag: float = 0.0
    series: int = 1
    parallel: int = 1
    voltage: float = 12.0
    drag: float = 0.0

    def __init__(self, *args, **kwargs):
        archtype = self.get_true_field('archtype', *args, **kwargs)
        weight = self.get_true_field('weight', *args, **kwargs)
        drag = self.get_true_field('drag', *args, **kwargs)
        if archtype == 'monolithic':
            batparams = {"series": 1, "parallel": 1,
                         "voltage": 12.0, "weight": weight, "drag": drag}
            compnames = ['s1p1']
        elif archtype == 'series-split':
            batparams = {'series': 2, 'parallel': 1,
                         'voltage': 12.0, "weight": weight, "drag": drag}
            compnames = ['s1p1', 's2p1']
        elif archtype == 'parallel-split':
            batparams = {'series': 1, 'parallel': 2,
                         'voltage': 12.0, "weight": weight, "drag": drag}
            compnames = ['s1p1', 's1p2']
        elif archtype == 'split-both':
            batparams = {'series': 2, 'parallel': 2,
                         'voltage': 12.0, "weight": weight, "drag": drag}
            compnames = ['s1p1', 's1p2', 's2p1', 's2p2']
        else:
            raise Exception("Invalid battery architecture")
        kwargs.update(batparams)
        super().__init__(*args, **kwargs)
        self.make_components(Battery, *compnames, p=batparams)


class StoreEEMode(Mode):
    """Overall StoreEE mode."""

    failrate = 1e-4
    faultparams = {'nocharge':  (0.2, {"taxi": 0.6, "move": 0.2, "land": 0.2}, 0),
                   'lowcharge': (0.7, {"taxi": 0.6, "move": 0.2, "land": 0.2}, 0)}
    key_phases_by = "plan_path"


class StoreEE(FxnBlock):
    """Class defining energy storage function with battery architecture."""

    __slots__ = ('hsig_bat', 'ee_1', 'force_st')
    _init_s = StoreEEState
    _init_m = StoreEEMode
    _init_ca = BatArch
    _init_hsig_bat = HSig
    _init_ee_1 = EE
    _init_force_st = Force

    def condfaults(self, time):
        """Calculate overall conditional faults for StoreEE architecture."""
        if self.s.soc < 20:
            self.m.add_fault('lowcharge')
        if self.s.soc < 1:
            self.m.replace_fault('lowcharge', 'nocharge')
        if self.m.has_fault('lowcharge'):
            for batname, bat in self.ca.components.items():
                bat.s.limit(soc=(0, 19))
        elif self.m.has_fault('nocharge'):
            for batname, bat in self.ca.components.items():
                bat.s.soc = 0

    def behavior(self, time):
        """Calculate overall behavior for StoreEE architecture."""
        ee, soc = {}, {}
        rate_res = 0
        for batname, bat in self.ca.components.items():
            ee[bat.name], soc[bat.name], rate_res = \
                bat.behavior(self.force_st.s.support, self.ee_1.s.rate /
                             (self.ca.series*self.ca.parallel)+rate_res, time)
        # need to incorporate max current draw somehow + draw when reconfigured
        if self.ca.archtype == 'monolithic':
            self.ee_1.s.effort = ee['s1p1']
        elif self.ca.archtype == 'series-split':
            self.ee_1.s.effort = np.max(list(ee.values()))
        elif self.ca.archtype == 'parallel-split':
            self.ee_1.s.effort = np.sum(list(ee.values()))
        elif self.ca.archtype == 'split-both':
            e = list(ee.values())
            e.sort()
            self.ee_1.effort = e[-1]+e[-2]
        self.s.soc = np.mean(list(soc.values()))
        if self.m.any_faults() and not self.m.has_fault("dummy"):
            self.hsig_bat.s.hstate = 'faulty'
        else:
            self.hsig_bat.s.hstate = 'nominal'


class HoldPayloadMode(Mode):
    """
    Landing Gear Modes.

    Modes
    -------
    break: Fault
        provides no support to the body and lines
    deform: Fault
        support is less than desired
    """

    failrate = 1e-6
    faultparams = {'break': (0.2, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 1000),
                   'deform': (0.8, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 1000)}
    key_phases_by = 'plan_path'


class HoldPayload(HoldPayloadDyn):
    """Adaptation of HoldPayload with new mode information."""

    _init_m = HoldPayloadMode


class ManageHealthMode(Mode):
    """
    Health management fault modes.

    Modes
    -------
    lostfunction: Fault
        Inability to sense health and thus reconfigure the system
    """

    failrate = 1e-6
    faultparams = {'lostfunction':
                   (0.05, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 1000)}
    key_phases_by = "plan_path"


class ManageHealth(FxnBlock):
    """Health management function for rotor and battery."""

    __slots__ = ('force_st', 'ee_ctl', 'hsig_dofs', 'hsig_bat', 'rsig_traj')
    _init_m = ManageHealthMode
    _init_p = ResPolicy
    _init_force_st = Force
    _init_ee_ctl = EE
    _init_hsig_dofs = HSig
    _init_hsig_bat = HSig
    _init_rsig_traj = RSig

    def condfaults(self, time):
        """If no support (e.g., in a crash), unit breaks."""
        if self.force_st.s.support < 0.5 or self.ee_ctl.s.effort > 2.0:
            self.m.add_fault('lostfunction')

    def behavior(self, time):
        """Assign recovery trajectory from ResPolicy for a fault mode, if found."""
        if self.m.has_fault('lostfunction'):
            self.rsig_traj.s.mode = 'continue'
        elif self.hsig_dofs.s.hstate == 'faulty':
            self.rsig_traj.s.mode = self.p.line
        elif self.hsig_bat.s.hstate == 'faulty':
            self.rsig_traj.s.mode = self.p.bat
        else:
            self.rsig_traj.s.mode = 'continue'


class AffectMode(Mode):
    """Overall Effect DOF mode - combines all line modes."""

    key_phases_by = 'plan_path'


class AffectDOF(AffectDOFHierarchical):
    """Adaptation of hierarchical AffecDOF function which returns fault signals."""

    __slots__ = ('hsig_dofs',)
    _init_m = AffectMode
    _init_hsig_dofs = HSig

    def reconfig_faults(self):
        """Send a faulty health state when in a fault mode."""
        AffectDOFHierarchical.reconfig_faults(self)
        if self.m.any_faults():
            self.hsig_dofs.s.hstate = 'faulty'
        else:
            self.hsig_dofs.s.hstate = 'nominal'


class CtlDOFMode(Mode):
    """
    Controller modes.

    Modes
    -------
    noctl: Fault
        No control transference (throttles set to zero)
    degctl: Fault
        Poor control transference (throttles set to 0.5)
    """

    failrate = 1e-5
    faultparams = {'noctl':   (0.2, {"taxi": 0.6, "move": 0.3, "land": 0.1}, 1000),
                   'degctl':  (0.8, {"taxi": 0.6, "move": 0.3, "land": 0.1}, 1000)}
    key_phases_by = 'plan_path'
    mode:   str = 'nominal'


class CtlDOF(CtlDOFStat):
    """Adaptation of CtlDOFMode with more mode information."""

    _init_m = CtlDOFMode


class PlanPathMode(Mode):
    """
    Path planning fault modes.

    Modes
    -------
    noloc: Fault
        no location data
    degloc: Fault
        degraded location data
    taxi: Mode
        off at landing area
    to_nearest: Mode
        go to the nearest possible landing area
    to_home: Mode
        flight to the takeoff location
    emland: Mode
        emergency landing
    land: Mode
        descent/landing
    move: Mode
        nominal drone navigation
    """

    failrate = 1e-5
    faultparams = {'noloc': (0.2, {"taxi": 0.6, "move": 0.3, "land": 0.1}, 1000),
                   'degloc': (0.8, {"taxi": 0.6, "move": 0.3, "land": 0.1}, 1000)}
    opermodes = ('taxi', 'to_nearest', 'to_home', 'emland', 'land', 'move')
    mode: str = 'taxi'
    exclusive = False
    key_phases_by = 'self'


class PlanPathState(PlanPathStateDyn):
    """
    Path planning states (extends dynamic model states for dynamic flightplan/height).

    Additional Fields
    -------
    ground_height : float
        Height above the ground (if terrain)
    goals : dict
        Sequence of goals defining the flightplan.
    """

    ground_height: float = 0.0
    goals: dict = {}


class PlanPath(PlanPathDyn):
    """Path planning function of the drone. Follows a sequence defined in flightplan."""

    __slots__ = ('rsig_traj', )
    _init_s = PlanPathState
    _init_m = PlanPathMode
    _init_p = DroneParam
    _init_rsig_traj = RSig
    default_track = {'s': ['ground_height', 'pt', 'goal'], 'm': 'all'}

    def __init__(self, name, flows, **kwargs):
        FxnBlock.__init__(self, name, flows, **kwargs)
        self.init_goals()

    def init_goals(self):
        """Initialize path planning goals based on initial flightplan."""
        self.s.goals = {i: list(vals) for i, vals in enumerate(self.p.flightplan)}

    def behavior(self, t):
        """
        Path planning behavior for the drone.

        The drone will (1) calculate distance to goal, (2) increment goal point,
        (3) update its internal mode and goal, and (3) assign a desired trajectory.
        """
        self.calc_dist_to_goal()
        self.increment_point()
        self.calc_ground_height()

        self.update_mode(t)
        self.update_goal()
        if self.ee_ctl.s.effort < 0.5 or self.m.in_mode('taxi'):
            self.des_traj.s.assign([0.0, 0.0, 0.0, 0.0], 'dx', 'dy', 'dz', 'power')
        else:
            self.des_traj.s.power = 1.0
            self.assign_vectdist_to_goal()

    def calc_ground_height(self):
        """Assigns the ground height state."""
        self.s.ground_height = self.dofs.s.z

    def update_mode(self, t):
        """Update mode based on current mode and state."""
        if not self.m.any_faults():
            # if in reconfigure mode, copy that mode, otherwise complete mission
            if self.rsig_traj.s.mode != 'continue' and not self.m.in_mode("move_em", "emland"):
                self.m.set_mode(self.rsig_traj.s.mode)
            elif self.m.in_mode('taxi') and t < 5 and t > 1:
                self.m.set_mode("move")
            # if mission is over, enter landing mode when you get close
            if self.mission_over():
                if self.dofs.s.z < 1:
                    self.m.set_mode('taxi')
                elif self.s.dist < 10:
                    if self.em_engaged():
                        self.m.set_mode('emland')
                    else:
                        self.m.set_mode('land')

    def update_goal(self):
        """Set the new goal based on the mode."""
        if self.m.in_mode('emland', 'land'):
            z_down = self.dofs.s.z - self.s.ground_height/2
            self.s.goal = (self.dofs.s.x, self.dofs.s.y, z_down)
        elif self.m.in_mode('to_home', 'taxi'):
            self.s.goal = self.p.flightplan[0]
        elif self.m.in_mode('to_nearest'):
            self.s.goal = (*self.p.safe[:2], 0.0)
        elif self.m.in_mode('move', 'move_em'):
            self.s.goal = self.s.goals[self.s.pt]
        elif self.m.in_mode('noloc'):
            self.s.goal = self.dofs.s.get('x', 'y', 'z')
        elif self.m.in_mode('degloc'):
            self.s.goal = self.dofs.s.get('x', 'y', 'z')
            self.s.goal[2] -= 1

    def em_engaged(self):
        """Return True if in an emergency mode already."""
        return 'em' in self.m.mode

    def update_traj(self):
        """Send commands (des_traj) if power."""
        if self.ee_ctl.s.effort < 0.5 or self.m.in_mode('taxi'):
            self.des_traj.s.assign([0.0, 0.0, 0.0, 0.0], 'x', 'y', 'z', 'power')
        else:
            self.des_traj.s.power = 1.0
            self.des_traj.s.assign(self.s, x='dx', y='dy', z='dz')

    def mission_over(self):
        """Return true if the mission is over (complete or in emergency mode)."""
        return (self.s.pt >= max(self.s.goals) or
                self.m.in_mode('to_nearest', 'to_home', 'land', 'emland'))

    def increment_point(self):
        """Increment to the next poin in the flight plan if close to goal point."""
        # if close to the given point, go to the next point
        if (self.m.in_mode('move', 'move_em')
                and self.s.dist < 10
                and self.s.pt < max(self.s.goals)):
            self.s.pt += 1


class Drone(Model):
    """Rural surveillance Drone model."""

    __slots__ = ('start_area', 'safe_area', 'target_area')
    _init_p = DroneParam
    default_sp = dict(phases=(('taxi', 0, 0),
                              ('move', 1, 11),
                              ('land', 12, 20)),
                      times=(0, 30), units='min')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # add flows to the model
        self.add_flow('force_st', Force)
        self.add_flow('force_lin', Force)
        self.add_flow('hsig_dofs', HSig)
        self.add_flow('hsig_bat', HSig)
        self.add_flow('rsig_traj', RSig)
        self.add_flow('ee_1', EE)
        self.add_flow('ee_mot', EE)
        self.add_flow('ee_ctl', EE)
        self.add_flow('ctl', Control)
        self.add_flow('dofs', DOFs)
        self.add_flow('des_traj', DesTraj)
        self.add_flow('environment', DroneEnvironment, p=self.p.env_param)

        # add functions to the model
        flows = ['ee_ctl', 'force_st', 'hsig_dofs', 'hsig_bat', 'rsig_traj']
        self.add_fxn('manage_health', ManageHealth, *flows, p=asdict(self.p.respolicy))

        store_ee_p = {'archtype': self.p.phys_param.bat,
                      'weight': self.p.phys_param.batweight+self.p.phys_param.archweight,
                      'drag': self.p.phys_param.archdrag}
        self.add_fxn('store_ee', StoreEE, 'ee_1', 'force_st', 'hsig_bat', ca=store_ee_p)
        self.add_fxn('dist_ee', DistEE, 'ee_1', 'ee_mot', 'ee_ctl', 'force_st')
        self.add_fxn('affect_dof', AffectDOF, 'ee_mot', 'ctl', 'dofs', 'des_traj',
                     'force_lin', 'hsig_dofs',
                     ca={'archtype': self.p.phys_param.linearch})
        self.add_fxn('ctl_dof', CtlDOF, 'ee_ctl', 'des_traj', 'ctl', 'dofs', 'force_st')
        self.add_fxn('plan_path', PlanPath, 'ee_ctl', 'dofs', 'des_traj', 'force_st',
                     'rsig_traj', p=asdict(self.p))
        self.add_fxn('hold_payload', HoldPayload, 'dofs', 'force_lin', 'force_st')
        self.add_fxn('view_environment', ViewEnvironment, 'dofs', 'environment')

        self.build()

    def at_start(self, dofs):
        """Check if drone is at start location."""
        return self.flows['environment'].c.in_area(dofs.s.x, dofs.s.y, 'start')

    def at_safe(self, dofs):
        """Check if drone is at a safe location."""
        return self.flows['environment'].c.in_area(dofs.s.x, dofs.s.y, 'safe')

    def at_dangerous(self, dofs):
        """Check if drone is at a dangerous location."""
        return self.flows['environment'].c.get(dofs.s.x, dofs.s.y, 'target')

    def calc_land_metrics(self, scen, faulttime):
        """
        Calculate landing metrics for the drone based on the scenario.

        Parameters
        ----------
        scen : Scenario
            Fault Scenario
        viewed : TYPE
            DESCRIPTION.
        faulttime : TYPE
            DESCRIPTION.

        Returns
        -------
        metrics : dict
            Metrics, including:
                - body_strikes
                - head_strikes
                - property_restrictions
                - safe_cost: safety cost
                - p_safety: probability of a safety-affecting event
                - severities: hazardous and minor event probabilities
        """
        metrics = {}
        dofs = self.flows['dofs']
        if self.at_start(dofs):
            landloc = 'nominal'  # nominal landing
        elif self.at_safe(dofs):
            landloc = 'designated'  # emergency safe
        elif self.at_dangerous(dofs):
            landloc = 'over target'  # emergency dangerous
        else:
            landloc = 'outside target'  # emergency unsanctioned
        # need a way to differentiate horizontal and vertical crashes/landings
        if landloc in ['over target', 'outside target']:
            if landloc == "outside target" and self.p.env_param.loc == 'congested':
                loc = 'urban'
            else:
                loc = self.p.env_param.loc
            metrics['body_strikes'] = density_categories[loc]['body strike']['horiz']
            metrics['head_strikes'] = density_categories[loc]['head strike']['horiz']
            metrics['property_restrictions'] = 1
        else:
            metrics['body_strikes'] = 0.0
            metrics['head_strikes'] = 0.0
            metrics['property_restrictions'] = 0
        metrics['safecost'] = calc_safe_cost(metrics, self.p.env_param.loc, faulttime)

        metrics['landcost'] = metrics['property_restrictions'] * \
            propertycost[self.p.env_param.loc]
        metrics['p_safety'] = calc_p_safety(metrics, faulttime)
        metrics['severities'] = {'hazardous': scen.rate * metrics['p_safety'],
                                 'minor': scen.rate * (1 - metrics['p_safety'])}
        return metrics

    def find_classification(self, scen, mdlhist):
        """Classify a given scenario based on land_metrics and expected cost model."""
        viewed = 0.5 + np.sum(self.flows['environment'].c.viewed*self.flows['environment'].c.target)
        # to fix: need to find fault time more efficiently (maybe in the toolkit?)
        faulttime = self.h.get_fault_time(metric='total')

        land_metrics = self.calc_land_metrics(scen, faulttime)

        # repair costs
        repcost = self.calc_repaircost(max_cost=1500)

        totcost = (land_metrics['landcost']
                   + land_metrics['safecost']
                   + repcost
                   - viewed)

        metrics = {'rate': scen.rate,
                   'cost': totcost,
                   'expected_cost': totcost * scen.rate * 1e5,
                   'repcost': repcost,
                   'viewed value': viewed,
                   'unsafe_flight_time': faulttime,
                   **land_metrics}
        return metrics

# BASE FUNCTIONS


def calc_p_safety(metrics, faulttime):
    """Calculate probability of a safety event."""
    p_saf = 1-np.exp(-(metrics['body_strikes'] + metrics['head_strikes']) * 60 /
                     (faulttime+0.001))  # convert to pfh
    return p_saf


def calc_safe_cost(metrics, loc, faulttime):
    """Calculate cost of a safety event."""
    safecost = safety_categories['hazardous']['cost'] * \
            (metrics['head_strikes'] + metrics['body_strikes']) + \
            unsafecost[loc] * faulttime
    return safecost


# PLOTTING
def plot_goals(ax, flightplan):
    for goal, loc in enumerate(flightplan):
        ax.text(loc[0], loc[1], loc[2], str(goal), fontweight='bold', fontsize=12)
        ax.plot([loc[0]], [loc[1]], [loc[2]], marker='o',
                markersize=10, color='red', alpha=0.5)


def plot_env_with_traj3d(hist, mdl):
    fig, ax = show.coord3d(mdl.flows['environment'].c, "target", z="",
                          collections={"start": {"color": "yellow"},
                                       "safe": {"color": "yellow"}})
    fig, ax = show.trajectories(hist, "dofs.s.x", "dofs.s.y", "dofs.s.z",
                                time_groups=['nominal'], time_ticks=1.0,
                                fig=fig, ax=ax)
    plot_goals(ax, mdl.p.flightplan)
    return fig, ax


def plot_env_with_traj(mdlhists, mdl):
    fig, ax = show.coord(mdl.flows['environment'].c, "target",
                        collections={"start": {"color": "yellow"},
                                     "safe": {"color": "yellow"}})
    fig, ax = show.trajectories(mdlhists, "dofs.s.x", "dofs.s.y", fig=fig, ax=ax)
    return fig, ax

# likelihood class schedule (pfh)
p_allowable = {'small airplane': {'no requirement': 'na',
                                  'probable': 1e-3,
                                  'remote': 1e-4,
                                  'extremely remote': 1e-5,
                                  'extremely improbable': 1e-6},
               'small helicopter': {'no requirement': 'na',
                                    'probable': 1e-3,
                                    'remote': 1e-5,
                                    'extremely remote': 1e-7,
                                    'extremely improbable': 1e-9}}

# population schedule
density_categories = {'congested': {'density': 0.006194,
                                    'body strike': {'vert': 0.1, 'horiz': 0.73},
                                    'head strike': {'vert': 0.0375, 'horiz': 0.0375}},
                      'urban': {'density': 0.002973,
                                'body strike': {'vert': 0.0004, 'horiz': 0.0003},
                                'head strike': {'vert': 0.0002, 'horiz': 0.0002}},
                      'suburban': {'density': 0.001042,
                                   'body strike': {'vert': 0.0001, 'horiz': 0.0011},
                                   'head strike': {'vert': 0.0001, 'horiz': 0.0001}},
                      'rural': {'density': 0.0001042,
                                'body strike': {'vert': 0.0000, 'horiz': 0.0001},
                                'head strike': {'vert': 0.000, 'horiz': 0.000}},
                      'remote': {'density': 1.931e-6,
                                 'body strike': {'vert': 0.0000, 'horiz': 0.0000},
                                 'head strike': {'vert': 0.000, 'horiz': 0.000}}}

unsafecost = {'congested': 1000, 'urban': 100, 'suburban': 25, 'rural': 5, 'remote': 1}
propertycost = {'congested': 100000, 'urban': 10000,
                'suburban': 1000, 'rural': 1000, 'remote': 1000}
# safety class schedule
safety_categories = {'catastrophic': {'injuries': 'multiple fatalities',
                                      'safety margins': 'na',
                                      'crew workload': 'na',
                                      'cost': 2000000},
                     'hazardous': {'injuries': 'single fatality and/or multiple serious injuries',
                                   'safety margins': 'large decrease',
                                   'crew workload': 'compromises safety',
                                   'cost': 9600000},
                     'major': {'injuries': 'non-serious injuries',
                               'safety margins': 'significant decrease',
                               'crew workload': 'significant increase',
                               'cost': 2428800},
                     'minor': {'injuries': 'na',
                               'safety margins':
                                   'slight decrease',
                                   'crew workload':
                                       'slight increase',
                                       'cost': 28800},
                     'no effect': {'injuries': 'na',
                                   'safety margins': 'na',
                                   'crew workload': 'na',
                                   'cost': 0}}

hazards = {'VH-1': 'loss of control',
           'VH-2': 'fly-away / non-conformance',
           'VH-3': 'loss of communication',
           'VH-4': 'loss of navigation',
           'VH-5': 'unsuccessful landing',
           'VH-6': 'unintentional flight termination',
           'VH-7': 'collision'}


if __name__ == "__main__":
    import fmdtools.sim.propagate as prop
    from fmdtools.analyze import show, plot

    mdl = Drone()

    ec, mdlhist = prop.nominal(mdl)
    phases, modephases = mdlhist.get_modephases()
    plot.phases(phases, modephases)

    mdl = Drone()
    app = SampleApproach(mdl,  phases={'move'})
    endclasses, mdlhists = prop.approach(mdl, app, staged=True)
    h = History(nominal=mdlhists.nominal,
                faulty=mdlhists.store_ee_lowcharge_t6p0)
    
    fault_kwargs = {'alpha': 0.2, 'color': 'red'}

    plot.hist(mdlhists, 'flows.dofs.s.x', 'dofs.s.y', 'dofs.s.z', 'store_ee.s.soc',
                 indiv_kwargs={'faulty': fault_kwargs})
    fig, ax = show.trajectories(mdlhists,
                                   "dofs.s.x", "dofs.s.y", "dofs.s.z",
                                   time_groups=['nominal'],
                                   indiv_kwargs={'faulty': fault_kwargs})
    
    fig, ax = show.trajectories(mdlhists, "dofs.s.x", "dofs.s.y",
                                time_groups=['nominal'],
                                indiv_kwargs={'faulty': fault_kwargs})
    
    
    fig, ax = plot_env_with_traj3d(h, mdl)
    fig, ax = plot_env_with_traj(mdlhists, mdl)
    
