# DeDe - The Depeche Demonstrator

DeDe is the technology demonstrator for the Depeche protocol. An overview of the
protocol itself is available at [the protocol site](https://depeche-protocol.github.io) -
The rest of this documentation will concern itself with DeDe itself.

## What it is

The Depeche Demonstrator is the proving grounds for protocol-related ideas and proposals.
New protocol additions should work in the demonstrator before they will be accepted - The
reason for this is that protocols that do not rub up against implementation realities
tend to be A) Hard to implement and B) Have loads of undocumented edge cases.

DeDe is written in Python 3 and not really meant for human consumption - At least not at
present. In its current shape it runs with a Curses interface in a Linux terminal, and
that is likely going to remain as long as I'm the only submitter.

## Dependencies

The crypto components are implemented in PyNaCL (at least 1.2.0), the database in SQLite 3.
Of course, these are implementation choices made for DeDe and not any kind of  mandate for
future implementations of the protocol itself.