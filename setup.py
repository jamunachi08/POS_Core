from setuptools import setup, find_packages

setup(
    name="alphax_pos_suite",
    version="15.9.10",
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
