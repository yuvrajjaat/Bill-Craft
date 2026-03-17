from jinja2 import Environment, FileSystemLoader
from pathlib import Path


def environment(**options):
    template_dir = Path(__file__).resolve().parent / 'templates'
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
        **options,
    )
    return env
