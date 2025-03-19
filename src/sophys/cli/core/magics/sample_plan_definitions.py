import functools

from .plan_magics import PlanCLI, ModeOfOperation, remote_control_available


if remote_control_available:
    from bluesky_queueserver_api.item import BPlan


class PlanMV(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("args", nargs='+', type=str)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        args, _, motors = self.parse_varargs(parsed_namespace.args, local_ns)

        md = self.parse_md(*motors, ns=parsed_namespace)

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, *args, md=md)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan.__name__, *args, md=md)
        if self._mode_of_operation == ModeOfOperation.Test:
            return (self._plan, args, md)


class PlanReadMany(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("devices", nargs='+', type=str)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        devices, _, names = self.parse_varargs(parsed_namespace.devices, local_ns)

        md = self.parse_md(*names, ns=parsed_namespace)

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, devices, md=md)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan.__name__, devices, md=md)
        if self._mode_of_operation == ModeOfOperation.Test:
            return (self._plan, devices, md)


class PlanCount(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-n", "--num", type=int, default=1)
        _a.add_argument("--delay", type=float, default=0.0)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        detectors = self.get_real_devices_if_needed(parsed_namespace.detectors, local_ns)
        num = parsed_namespace.num
        delay = parsed_namespace.delay

        md = self.parse_md(*parsed_namespace.detectors, ns=parsed_namespace)

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, detectors, num=num, delay=delay, md=md)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan_name, detectors, num=num, delay=delay, md=md)
        if self._mode_of_operation == ModeOfOperation.Test:
            return (self._plan, detectors, num, delay, md)


class PlanScan(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-m", "--motors", nargs='+', type=str)
        _a.add_argument("-n", "--num", type=int, default=-1)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        detectors = self.get_real_devices_if_needed(parsed_namespace.detectors, local_ns)
        _args = parsed_namespace.motors
        _num = parsed_namespace.num
        args, num, motors = self.parse_varargs(_args, local_ns, with_final_num=(_num == -1), default_num=_num)

        md = self.parse_md(*parsed_namespace.detectors, *motors, ns=parsed_namespace)

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, detectors, *args, num=num, md=md)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan_name, detectors, *args, num=num, md=md)
        if self._mode_of_operation == ModeOfOperation.Test:
            return (self._plan, detectors, args, num, md)


class PlanGridScan(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-m", "--motors", nargs='+', type=str)
        _a.add_argument("-s", "--snake_axes", action="store_true", default=False)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        detectors = self.get_real_devices_if_needed(parsed_namespace.detectors, local_ns)
        _args = parsed_namespace.motors
        args, _, motors = self.parse_varargs(_args, local_ns)

        md = self.parse_md(*parsed_namespace.detectors, *motors, ns=parsed_namespace)

        snake = parsed_namespace.snake_axes

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, detectors, *args, snake_axes=snake, md=md)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan_name, detectors, *args, snake_axes=snake, md=md)
        if self._mode_of_operation == ModeOfOperation.Test:
            return (self._plan, detectors, args, snake, md)


class PlanAdaptiveScan(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-t", "--target_field", type=str)
        _a.add_argument("-m", "--motor", type=str)
        _a.add_argument("-st", "--start", type=float)
        _a.add_argument("-sp", "--stop", type=float)
        _a.add_argument("-mins", "--min_step", type=float)
        _a.add_argument("-maxs", "--max_step", type=float)
        _a.add_argument("-td", "--target_delta", type=float)
        _a.add_argument("-b", "--backstep", type=bool)
        _a.add_argument("-th", "--threshold", type=float, default=0.8)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        detectors = self.get_real_devices_if_needed(parsed_namespace.detectors, local_ns)
        motor = self.get_real_devices_if_needed(parsed_namespace.motor, local_ns)

        md = self.parse_md(*parsed_namespace.detectors, parsed_namespace.motor, ns=parsed_namespace)

        target_field = parsed_namespace.target_field
        start = parsed_namespace.start
        stop = parsed_namespace.stop
        min_step = parsed_namespace.min_step
        max_step = parsed_namespace.max_step
        target_delta = parsed_namespace.target_delta
        backstep = parsed_namespace.backstep
        threshold = parsed_namespace.threshold

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, detectors, target_field=target_field, motor=motor, start=start, stop=stop, min_step=min_step, max_step=max_step, target_delta=target_delta, backstep=backstep, threshold=threshold, md=md)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan_name, detectors, target_field=target_field, motor=motor, start=start, stop=stop, min_step=min_step, max_step=max_step, target_delta=target_delta, backstep=backstep, threshold=threshold, md=md)
        if self._mode_of_operation == ModeOfOperation.Test:
            return (self._plan, detectors, target_field, motor, start, stop, min_step, max_step, target_delta, backstep, threshold, md)
