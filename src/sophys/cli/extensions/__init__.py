import functools

from .. import BANNER_NAME_EXTEND


def in_debug_mode(local_ns):
    return local_ns["DEBUG"]


@functools.lru_cache(maxsize=1)
def render_custom_magics(ipython):
    render = []
    render.append("")
    render.append("The custom available commands are:")
    for registered_magics in ipython.magics_manager.registry.values():
        if hasattr(registered_magics, "description"):
            render.append("\n".join(f"{name:<{BANNER_NAME_EXTEND}}: {desc}" for name, desc in registered_magics.description()))
    render.append("")
    render.append("")
    return render
