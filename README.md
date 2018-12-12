# sphinxify
Convert Javadoc and Doxygen to Sphinx docstrings.

## Why?
The [RobotPy][] project ports Java libraries to Python.

A converter was originally written in HTML + JavaScript, but then the need to
be able to programmatically convert doc comments arose.

This also makes it easier to use in certain editors such as vim...

## Usage
Run `sphinxify` and give it a Javadoc comment.  It will keep reading until EOF.

If a Java function prototype is also given, sphinxify will also output a
Python type-hinted function signature.

There is also a `sphinxify yaml` mode for the [robotpy-ctre][].

[RobotPy]: https://robotpy.github.io
[robotpy-ctre]: https://github.com/robotpy/robotpy-ctre
