from setuptools import find_packages, setup

setup(
    name="segment_speed_utils",
    packages=find_packages(),
    version="0.1.0",
    description="Utility functions for GTFS RT segment speeds",
    author="Cal-ITP",
    license="Apache",
    include_package_data=True,
    package_dir={"segment_speed_utils": "segment_speed_utils"},
)