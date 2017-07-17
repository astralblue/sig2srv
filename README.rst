=======
sig2srv
=======


.. image:: https://img.shields.io/pypi/v/sig2srv.svg
        :target: https://pypi.python.org/pypi/sig2srv

.. image:: https://img.shields.io/travis/astralblue/sig2srv.svg
        :target: https://travis-ci.org/astralblue/sig2srv

.. image:: https://readthedocs.org/projects/sig2srv/badge/?version=latest
        :target: https://sig2srv.readthedocs.io/en/latest/?badge=latest
        :alt: Documentation Status

.. image:: https://pyup.io/repos/github/astralblue/sig2srv/shield.svg
     :target: https://pyup.io/repos/github/astralblue/sig2srv/
     :alt: Updates


sig2srv converts incoming signals into suitable service(8) commands.


* Free software: MIT license
* Documentation: https://sig2srv.readthedocs.io.


Features
--------

* Turns SIGTERM into "service XYZ stop" commands.
* Turns SIGHUP into "service XYZ restart" commands.
* Runs "service XYZ status" periodically and exits with a nonzero status if the
  service is no longer seen as running, i.e. the status command returns a
  nonzero status.

Credits
---------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage

