# coding: utf-8
#
# This code is part of alftools.
#
# Copyright (c) 2022, Dylan Jones

import os
import numpy as np
from .utils import ParseError, ComplexParseError, csv_to_complex, strings_to_numbers
import itertools


def _rename_keys(d, key_map) -> None:
    """Renames the keys of a dictionary according to the `key_map`."""
    for old, new in key_map.items():
        if old in d:
            d[new] = d[old]
            del d[old]


def read_info_file(path: str, key_map=None):
    if not path.endswith("_info"):
        raise ValueError(f"File {path} is not a ALF info file!")

    # Read info file contents
    with open(path, "r") as fh:
        data = fh.read()

    # Parse info data to a dict with numerical values (if possible)
    info = dict()
    for line in data.splitlines():
        line = line.strip()
        if not line.startswith("="):
            try:
                if ": " in line:
                    name, valuestr = line.split(": ")
                    values = [s.strip() for s in valuestr.split()]
                    info[name.strip().lower()] = strings_to_numbers(values)
                else:
                    info[line.strip().lower()] = ""
            except ValueError as e:
                raise ParseError(f"Couldn't parse info-line '{line}': {e}")

    # Rename some keys
    default_key_map = {
        "number of orbitals": "norbs",
        "unit cells": "ncells"
    }
    if key_map is not None:
        default_key_map.update(key_map)
    _rename_keys(info, default_key_map)

    return info


def rebin(x, nrebin):
    """Combine each N_rebin bins into one bin.

    If the number of bins (=N0) is not an integer multiple of N_rebin,
    the last N0 modulo N_rebin bins get dismissed.
    """
    if nrebin == 1:
        return x
    n0 = len(x)
    n = n0 // nrebin
    shape = (n,) + x.shape[1:]
    y = np.empty(shape, dtype=x.dtype)
    for i in range(n):
        y[i] = np.mean(x[i * nrebin:(i + 1) * nrebin], axis=0)
    return y


def jack(x, nrebin, nskip):
    """
    Create jackknife bins out of input bins after after skipping and rebinning.

    Parameters
    ----------
    x : array-like object
        Input bins. Bins run over first index.
    nskip : int, default=par.N_skip()
        Number of bins to skip.
    nrebin : int, default=par.N_rebin()
        Number of bins to recombine into one.

    Returns
    -------
    numpy array
        Jackknife bins after skipping and rebinning.
    """
    if nskip != 0:
        x = x[nskip:]
    x = rebin(x, nrebin)
    n = len(x)
    y = (np.sum(x, axis=0) - x) / (n-1)
    return y


def read_data_tau(root, name):
    info = read_info_file(os.path.join(root, name + "_info"))
    ntau = info["ntau"]
    ncells = info["ncells"]
    norbs = info["norbs"]
    dtau = info["dtau"]

    path = os.path.join(root, name)
    with open(path, "r") as fh:
        data = fh.read()
    lines = data.splitlines()

    num_bins0 = len(lines) / (1 + norbs + ncells + ncells * ntau * norbs ** 2)
    num_bins = int(round(num_bins0))
    if abs(num_bins0 - num_bins) > 1e-10:
        raise ParseError(
            f"Error in reading data: File '{path}', line number does not fit!"
            "Did you forget to clear the output-dir before re-running the simulation?"
        )
    values = np.zeros((num_bins, norbs, norbs, ntau, ncells), dtype=np.complex128)
    signs = np.zeros(num_bins, dtype=np.int8)
    backs = np.zeros((num_bins, norbs), dtype=np.complex128)

    i = 0
    for ibin in range(num_bins):
        # Parse header line and check parameters
        header = lines[i].split()
        signs[ibin] = float(header[0])
        assert int(header[1]) == norbs
        assert int(header[2]) == ncells
        assert int(header[3]) == ntau
        assert float(header[4]) == dtau
        i += 1

        # First `norbs` lines for background
        for iorb in range(norbs):
            backs[ibin, iorb] = csv_to_complex(lines[i])
            i += 1

        # Parse main data
        for icell in range(ncells):
            # What is this line??? (without braces)
            # line = lines[i]
            # val1, val2 = [_string_to_number(s) for s in line.split()]
            # print(val1, val2)
            i += 1
            for itau in range(ntau):
                for orb1, orb2 in itertools.product(range(norbs), repeat=2):
                    line = lines[i]
                    try:
                        values[ibin, orb1, orb2, itau, icell] = csv_to_complex(line)
                    except ValueError:
                        raise ComplexParseError(lines[i])
                    i += 1

    nrebin, nskip = 1, 1
    values = jack(values, nrebin, nskip)
    # backs = jack(backs, nrebin, nskip)
    signs = jack(signs, nrebin, nskip)
    return info, values, signs


def read_gftau(root, normalize=True):
    info, gf_tau, signs = read_data_tau(root, "Green_tau")
    tau = np.arange(info["ntau"]) * info["dtau"]
    if normalize:
        gf_tau /= info["ncells"] * info["norbs"]
    return info, tau, gf_tau, signs
