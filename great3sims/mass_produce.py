# Copyright (c) 2014, the GREAT3 executive committee (http://www.great3challenge.info/?q=contacts)
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted
# provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions
# and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of
# conditions and the following disclaimer in the documentation and/or other materials provided with
# the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to
# endorse or promote products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
# IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
# OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""This is a script that can be used for mass-production of sims on a cluster (and was used to
generate the simulations for GREAT3).  Currently it is set up for the Warp and Coma clusters at CMU,
but hopefully should not be too painful to repurpose elsewhere, particularly on a machine that also
uses PBS for the queueing system.  At minimum, there are some directories and such that will have to
be changed to point to the right place on other systems."""
import time
import os
import subprocess
import sys
import shutil
import mass_produce_utils
import getpass

sys.path.append('..')
import great3sims

# Define some basic parameters.  This includes some system-dependent things like directories for
# output.
root = '/physics/rmandelb/great3-v11'
# Number of config files to be run per branch.
n_config_per_branch = 10
# The total number of subfields is split up into n_config_per_branch config files.
subfield_min = 0
subfield_max = 204
gal_dir = '/lustre/rmandelb/great3_fit_data'
ps_dir = '/home/rmandelb/git/great3-private/inputs/shear-ps/tables'
seed = 31415
public_dir = 'public'
# amount to increment seed for each successive branch
delta_seed = 137
# seconds between checks for programs to be done
sleep_time = 30
package_only = False # only do the packaging and nothing else
do_images = True  # Make images or not?  If False with package_only also False, then just skip the
                  # image-making step: remake catalogs but do not delete files / dirs with images,
                  # then package it all up.
do_gal_images = True # Make galaxy images?  If do_images = True, then do_gal_images becomes
                     # relevant; it lets us only remake star fields if we wish (by having do_images
                     # = True, do_gal_images = False).
preload = False # preloading for real galaxy branches - irrelevant for others.
# Do we want to be nice to others in the queue by rationing the number of image generation scripts
# to be submitted simultaneously?  Or just submit them all, perhaps because there are so few that it
# isn't rude to do them all at once?  If `queue_nicely = False`, then dump them all at once.  If
# `queue_nicely` is set to some number, it means that number is the maximum number to have in the
# queue at once.
queue_nicely = 13

# Set which branches to test.
experiments = [
    'control',
    'real_galaxy',
    'variable_psf',
    'multiepoch',
    'full',
]
obs_types = [
    'ground',
    'space',
]
shear_types = [
    'constant',
    'variable',
]
branches = [ (experiment, obs_type, shear_type)
             for experiment in experiments
             for obs_type in obs_types
             for shear_type in shear_types]
n_branches = len(branches)
print "Producing images for ",n_branches," branches"

if not package_only:
    if do_images:
        # Clean up from previous runs
        shutil.rmtree(root, ignore_errors=True)

    # First we set up a process for each branch.  We use a different random seed for each, and we do
    # the following steps: metaparameters, catalogs, config.  For config, there is some additional
    # juggling to do for config file names / dirs.
    prefix1 = 'g3_step1_'
    all_config_names = []
    for experiment, obs_type, shear_type in branches:
        e = experiment[0]
        o = obs_type[0]
        s = shear_type[0]

        pbs_name = prefix1+e+o+s
        pbs_file = pbs_name+'.sh'
        python_file = pbs_name+'.py'

        # Write out some scripts.
        mass_produce_utils.pbs_script_python(pbs_file, pbs_name)
        new_config_names, new_psf_config_names, new_star_test_config_names = \
            mass_produce_utils.python_script(python_file, root, subfield_min, subfield_max,
                                             experiment, obs_type, shear_type, gal_dir, ps_dir,
                                             seed, n_config_per_branch, preload, my_step=1)
        if do_gal_images:
            for config_name in new_config_names:
                all_config_names.append(config_name)
        for psf_config_name in new_psf_config_names:
            all_config_names.append(psf_config_name)
        for star_test_config_name in new_star_test_config_names:
            all_config_names.append(star_test_config_name)
        seed += delta_seed

    print "Wrote files necessary to carry out metaparameters, catalogs, and config steps"
    t1 = time.time()
    for experiment, obs_type, shear_type in branches:
        e = experiment[0]
        o = obs_type[0]
        s = shear_type[0]

        pbs_name = prefix1+e+o+s
        pbs_file = pbs_name+'.sh'
        command_str = 'qsub '+pbs_file
        p = subprocess.Popen(command_str,shell=True,close_fds=True)
    # The above command just submitted all the files to the queue.  We have to periodically poll the
    # queue to see if they are still running.
    mass_produce_utils.check_done('g3_step1', sleep_time=sleep_time)
    t2 = time.time()
    # Times are approximate since check_done only checks every N seconds for some N
    print
    print "Time for generation of metaparameters, catalogs, and config files = ",t2-t1
    print

    if do_images:
        # Then we split up into even more processes for images.
        t1 = time.time()
        prefix2 = 'g3_step2_'
        for config_name in all_config_names:
            file_type, _ = os.path.splitext(config_name)
            pbs_file = prefix2 + file_type+'.sh'
            mass_produce_utils.pbs_script_yaml(pbs_file, config_name, root)
            command_str = 'qsub '+pbs_file
            if queue_nicely:
                mass_produce_utils.check_njobs('g3_', sleep_time=sleep_time, n_jobs=queue_nicely)
            p = subprocess.Popen(command_str, shell=True, close_fds=True)
        mass_produce_utils.check_done('g3_', sleep_time=sleep_time)
        t2 = time.time()
        # Times are approximate since check_done only checks every N seconds for some N
        print
        print "Time for generation of images = ",t2-t1
        print

# Finally, we go back to a process per branch for the final steps: star_params and packages.
t1 = time.time()
prefix3 = 'g3_step3_'
for experiment, obs_type, shear_type in branches:
    e = experiment[0]
    o = obs_type[0]
    s = shear_type[0]

    pbs_name = prefix3+e+o+s
    pbs_file = pbs_name+'.sh'
    python_file = pbs_name+'.py'

    # Write out some scripts.
    mass_produce_utils.pbs_script_python(pbs_file, pbs_name)
    mass_produce_utils.python_script(python_file, root, subfield_min, subfield_max, experiment,
                                     obs_type, shear_type, gal_dir, ps_dir, seed,
                                     n_config_per_branch, preload, my_step=3, public_dir=public_dir)
    # And then submit them
    command_str = 'qsub '+pbs_file
    p = subprocess.Popen(command_str,shell=True, close_fds=True)
# The above command just submitted all the files to the queue.  We have to periodically poll the
# queue to see if they are still running.
mass_produce_utils.check_done('g3_step3', sleep_time=sleep_time)
t2 = time.time()
# Times are approximate since check_done only checks every N seconds for some N
print
print 'Time for great3sims.run star_params, packages = ',t2-t1
print
