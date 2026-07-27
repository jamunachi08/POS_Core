import re
from pathlib import Path

from setuptools import setup, find_packages


def get_version():
    """Single source of truth. setup.py and __init__.py drifted once
    (15.9.10 vs 15.10.0); reading it here means they cannot again."""
    text = Path("alphax_pos_suite/__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*[\'\"]([^\'\"]+)', text).group(1)

setup(
    name="alphax_pos_suite",
    version=get_version(),
    description="AlphaX Bonanza POS Pack (XPOS + αPOS) for ERPNext/Frappe v15+",
    author="AlphaX",
    packages=find_packages(),
    include_package_data=True,
    # Explicitly carry every static asset into the wheel so /assets/<app>/...
    # is always served, even when the platform installs the app as a package.
    package_data={
        "alphax_pos_suite": [
            "public/**/*",
            "www/**/*",
            "config/**/*",
            "fixtures/**/*",
        ],
        "alphax_pos_suite.alphax_pos_suite": [
            "public/**/*",
            "www/**/*",
            "templates/**/*",
            "fixtures/**/*",
            "config/**/*",
            "*.json",
            "*.css",
            "*.js",
            "*.html",
        ],
    },
    zip_safe=False,
    install_requires=["frappe>=15.0.0"],
)
