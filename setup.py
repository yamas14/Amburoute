from setuptools import setup, find_packages
#nigga
with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="amburoute",
    version="1.0.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=requirements,
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "amburoute=__main__:main",
        ],
    },
)
