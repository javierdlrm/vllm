import os
import argparse
import importlib
import inspect

from fastapi import Request

from vllm.utils import FlexibleArgumentParser

SUPPORTED_INIT_ARGS = {"project", "deployment", "model"}


def add_cli_args(parser: FlexibleArgumentParser):
    # model_name is set by both KServe and Hopsworks backend
    parser.add_argument("--model_name", help="model name.", required=True)
    # api_protocol, only V1 will be received. This argument is not used in this vllm server
    parser.add_argument(
        "--api_protocol",
        default="v1",
        type=str,
        choices=[
            "v1",
            # PredictorProtocol.REST_V2.value,
            # PredictorProtocol.GRPC_V2.value,
        ],
        help="The inference protocol used for calling to the predictor.",
    )
    # predictor script file
    parser.add_argument(
        "-f",
        "--file",
        help="user-supplied script that implements the component class Predict or Predictor.",
        default=None,
    )


def validate_parsed_serve_args(args: argparse.Namespace):
    if not args.served_model_name:
        # if served-model-name not provided, use the model-name set by Hopsworks backend
        args.served_model_name = args.model_name


def _parse_module_name(file_path):
    """Parse a file_path to module name for dynamic import"""
    file_name = file_path if "/" not in file_path else os.path.split(file_path)[1]
    return os.path.splitext(file_name)[0]


def _get_component_class(component: any):
    # Check for 'Predict' class first to make sure that old predictor scripts that
    # can potentially contain a Predictor class will still work.

    try:
        return component.Predict
    except AttributeError:
        pass
    try:
        return component.Predictor
    except AttributeError:
        pass
    raise RuntimeError(
        "The provided predictor script does not implement a class named 'Predict' or 'Predictor'."
    )


def _initialize_component(component_class):
    # extract user-requested handles
    sig = inspect.signature(component_class)
    # validate sig.parameters
    if not SUPPORTED_INIT_ARGS.issuperset(sig.parameters):
        raise RuntimeError(
            component_class.__name__
            + " class constructor contains one or more unsupported parameters. "
            + "Valid parameters are 'project', 'deployment' and 'model'."
        )
    # build requested handles
    kwargs = {}
    if len(sig.parameters):
        kwargs = _login_and_get_requested_handles(sig.parameters)
    # initialize component
    component = component_class(**kwargs)
    # add helper attributes
    component._has_apply_chat_template = hasattr(
        component, "apply_chat_template"
    ) and callable(component.apply_chat_template)
    component._has_create_completion = hasattr(
        component, "create_completion"
    ) and callable(component.create_completion)
    component._has_create_chat_completion = hasattr(
        component, "create_chat_completion"
    ) and callable(component.create_chat_completion)

    return component


def _login_and_get_requested_handles(self, sig_parameters):
    """Connect with Hopsworks and return the Hopsworks assets requested by the user"""
    import hopsworks

    kwargs = {}
    # connect to hopsworks
    project = hopsworks.login()
    if "project" in sig_parameters:
        kwargs["project"] = project
    # check deployment handle
    if "deployment" in sig_parameters:
        kwargs["deployment"] = project.get_model_serving().get_deployment(
            os.environ["DEPLOYMENT_NAME"]
        )
    # check model handle
    if "model" in sig_parameters:
        kwargs["model"] = project.get_model_registry().get_model(
            os.environ["MODEL_NAME"], os.environ["MODEL_VERSION"]
        )

    return kwargs


def load_component_module(args: argparse.Namespace):
    if not args.file:
        # no predictor script specified
        return None

    module_name = _parse_module_name(args.file)
    spec = importlib.util.spec_from_file_location(module_name, args.file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    component_class = _get_component_class(mod)
    return _initialize_component(component_class)


def get_component_from_state(request: Request):
    return request.app.state.component
