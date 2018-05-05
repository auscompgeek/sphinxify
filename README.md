# sphinxify
Convert Javadoc (and Doxygen, maybe) to Sphinx docstrings.

## Why?
The [RobotPy][] project ports Java libraries to Python.

A converter was originally written in HTML + JavaScript, but then the need to
be able to programmatically convert doc comments arose.

This also makes it easier to use in certain editors such as vim...

## Usage
Run `sphinxify` and give it some input.  It will keep reading until EOF.

There is also a `sphinxify yaml` mode for the [robotpy-ctre][].

[RobotPy]: https://robotpy.github.io
[robotpy-ctre]: https://github.com/robotpy/robotpy-ctre
