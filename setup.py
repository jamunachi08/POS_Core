from setuptools import setup, find_packages

setup(
    name="alphax_pos_suite",
    version="15.5.22",
    description="AlphaX Bonanza POS Pack (XPOS + αPOS) for ERPNext/Frappe v15+",
    author="AlphaX",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
)
