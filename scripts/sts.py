#!/usr/bin/env python
import numpy as np
#import matplotlib.pyplot as plt
import argparse
import atk.format.cp2k as cp2k
import atk.util.progressbar as progressbar
import os.path

# Define command line parser
parser = argparse.ArgumentParser(
    description='Perform Scanning Tunneling Simulation.')
parser.add_argument('--version', action='version', version='%(prog)s 13.12.2013')
parser.add_argument(
    'cubes',
    nargs='+',
    metavar='cube files',
    help='The cube files to be sliced')
parser.add_argument(
    '--psisquared',
    metavar='True/False',
    default=False,
    type=bool,
    help='True, if cube files contain the density (psi squared).')
parser.add_argument(
    '--levelsfile',
    metavar='levels file',
    required=True,
    help='File containing the energy levels.')
parser.add_argument(
    '--outfile',
    metavar='output file',
    default='sts.cube',
    help='Name of cube file for STS simulation.')
parser.add_argument(
    '--emin',
    metavar='value',
    default=-3.0,
    type=float,
    help='Minimum bias for STS [V].')
parser.add_argument(
    '--emax',
    metavar='value',
    default=+3.0,
    type=float,
    help='Maximum bias for STS [V].')
parser.add_argument(
    '--de',
    metavar='value',
    default=+0.01,
    type=float,
    help='Bias step for STS [V].')
parser.add_argument(
    '--sigma',
    default=+0.075,
    type=float,
    help='sigma of Gaussian broadening [V]. FWHM = 2.355 sigma.')
parser.add_argument(
    '--nsigmacut',
    default=5,
    type=int,
    help='At a given energy E, consider levels within window [E-nsigmacut*sigma,E+nsigmacut*sigma].')
parser.add_argument(
    '--dz',
    metavar='delta z',
    default=2.5,
    type=float,
    help='The height above the topmost atom, where to extract the plane.')
parser.add_argument(
    '--eref',
    default=None,
    metavar='reference energy',
    type=float,
    help='By default, Fermi is taken as zero-energy reference. With this option\
          it is possible to define a different reference')
parser.add_argument(
    '--normalize',
    default=False,
    type=bool,
    help='Whether to normalize the STS intensity to 1.')
#parser.add_argument(
#    '--rep',
#    default=None,
#    nargs='+',
#    type=int, 
#    metavar='nx ny',
#    help='Number of replica along x and yi. If just one number is specified, it is taken for both x and y.')

args = parser.parse_args()

gaussian = lambda x: 1/(args.sigma * np.sqrt(2*np.pi)) \
                     * np.exp( - x**2 / (2 * args.sigma**2) )

spectrum = cp2k.Spectrum.from_mo(args.levelsfile)
print("Read spectrum from {f}".format(f=args.levelsfile))
print(spectrum)

if args.eref is not None:
    spectrum.shift(-args.eref)
    print("Taking {s} eV as zero energy reference.".format(s=args.eref))
else:
    for spin, levels in zip(spectrum.spins, spectrum.energylevels):
        levels.shift(-levels.fermi)
    print("Fermi energy is taken as zero energy reference.")

# Reading headers of cube files
cubes = []
print("\nReading headers of {n} cube files".format(n=len(args.cubes)))
bar = progressbar.ProgressBar(niter=len(args.cubes))

for fname in args.cubes:
    cubes.append( cp2k.WfnCube.from_file(fname) )
    bar.iterate()

# Connecting energies with required cube files
required_cubes = []
for spin, levels in zip(spectrum.spins, spectrum.energylevels):
    for index, l in enumerate(levels.levels):
        e = l.energy
        o = l.occupation
        # If we need the cube file for this level..
        if e >= args.emin - args.sigma * args.nsigmacut and \
           e <= args.emax + args.sigma * args.nsigmacut:

               found = False
               for cube in cubes:
                   #print "ind {}  {} spin {} {}".format(cube.wfn,index,cube.spin,spin)
                   if cube.wfn == index and cube.spin == spin + 1:
                       cube.energy = e
                       cube.occupation = o
                       required_cubes.append(cube)
                       found = True

                       print("Found cube file for spin {s}, energy {e}, occupation {o}"\
                             .format(s=spin+1,e=e, o=o))
                       break
               if not found:
                   print("Missing cube file for spin {s}, energy {e}, occupation {o}"\
                           .format(s=spin+1,e=e,o=o))

# Prepare new cube file
print("\nInitializing STS cube")
stscube = cp2k.WfnCube.from_file(required_cubes[0].filename, read_data=True)

stscube.title = "STS data (z axis = energy)"
stscube.comment = "Range [{:4.2f} V, {:4.2f} V], de {:4.3f} V, sigma {:4.3f} V" \
               .format(args.emin, args.emax, args.de, args.sigma)
# adjust z-dimension for energy
shape = np.array(stscube.data.shape)
shape[2] = int( (args.emax - args.emin) / args.de) + 1
stscube.data = np.zeros(shape)
stscube.origin[2] = args.emin

zrange = np.r_[stscube.origin[2], args.emax, shape[2]]

# Perform STS calculation
print("\nReading data of {n} cube files".format(n=len(required_cubes)))
bar = progressbar.ProgressBar(niter=len(required_cubes))

for cube in required_cubes:

    # Reading cube files is the most time consuming part of the routine.
    # Since we need only one plane out of each cube file,
    # we save it to disk for reuse.
    planefile = "{f}.dz{d}".format(f=cube.filename,d=args.dz)
    if( os.path.isfile(planefile) ):
        plane = np.genfromtxt(planefile)

    else:
        # We don't want to keep all cubes in memory at once
        tmp = cp2k.WfnCube.from_cube(cube)
        tmp.read_cube_file(tmp.filename,read_data=True)
        if(not args.psisquared):
            tmp.data = np.square(tmp.data)

        plane = tmp.get_plane_above_atoms(args.dz)
        # For STS, the occupation of the level is irrelevant
        #plane = plane * tmp.occupation
        np.savetxt(planefile, plane)

    emin = tmp.energy - args.sigma * args.nsigmacut
    emax = tmp.energy + args.sigma * args.nsigmacut
    imin = (np.abs(zrange-emin)).argmin()
    imax = (np.abs(zrange-emax)).argmin()

    for i in range(imin,imax+1):
        stscube.data[:,:,i] += plane * gaussian(tmp.energy - zrange[i])

    bar.iterate()

#TODO: Normalize, if asked to
#if args.normalize:
#   stscube.data /= np.sum(stscube.data)


print("Writing {}".format(args.outfile))
sts.cube.write_cube_file(args.outfile)

    
