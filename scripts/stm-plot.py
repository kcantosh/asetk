#!/usr/bin/env python
import numpy as np
import argparse
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab

import asetk.format.cube as cube
import asetk.format.igor as igor
import sys

def resample(plane, cube, rep=None, nsamples=1000):
    """Resamples data in cartesian coordinates.

    Assumptions:
    - data.shape == [self.data.shape[i] for i in axes]
    """
    nx,ny,nz    = cube.data.shape
    dx,dy,dz    = cube.atoms.cell / cube.data.shape

    if rep:
        plane = np.tile(plane, rep)
        nx *= rep[0]
        ny *= rep[1]
        
    plane = plane.flatten()
    pos   = [ i*dx+j*dy for i in range(nx) for j in range(ny) ]
    x,y,z = zip(*pos)

    extent = (np.min(x),np.max(x),np.min(y),np.max(y))
    xnew = np.linspace(extent[0], extent[1], nsamples)
    ynew = np.linspace(extent[2], extent[3], nsamples)

    # default interp='nn' needs mpl_toolkits.natgrid,
    # which doesn't work on some machines
    #resampled = mlab.griddata(x, y , plane, xnew, ynew)
    resampled = mlab.griddata(x, y , plane, xnew, ynew, interp='linear')
    # for some reason, I need to revert the x axis for imshow
    resampled = resampled[::-1,:]

    return [resampled, extent]


# Define command line parser
parser = argparse.ArgumentParser(
    description='Plots Scanning Tunneling Microscopy Image from Gaussian Cube file.')
parser.add_argument('--version', action='version', version='%(prog)s 17.03.2014')
parser.add_argument(
    '--stmcubes',
    nargs='+',
    metavar='FILENAMES',
    help='Cube files containing the local density of states (s-wave tip)\
          or the appropriate matrix elements (general case).')
parser.add_argument(
    '--heights',
    nargs='+',
    metavar='LIST',
    type=float,
    help='Tip-height above the topmost atom for an STM-image in constant-z\
          mode. 3 Angstroms is typically reasonable.')
parser.add_argument(
    '--isovalues',
    nargs='+',
    metavar='LIST',
    type=float,
    help='Values of the isosurface for an STM-image in constant current mode.\
          1e-7 is typically a good start.')
parser.add_argument(
    '--zmin',
    metavar='HEIGHT',
    type=float,
    default=0.0,
    help='Minimum z-height [Angstroms] for the tip inr constant-current mode.')
parser.add_argument(
    '--noplot',
    dest='plot',
    action='store_false',
    default=True,
    help='Suppress plotting of resulting isosurface using matplotlib.')
parser.add_argument(
    '--plotrange',
    nargs='+',
    metavar='MIN MAX',
    default=None,
    type=float,
    help='Range of color scale in plot')
parser.add_argument(
    '--replicate',
    default=None,
    nargs='+',
    type=int, 
    metavar='nx ny',
    help='Number of replica along x and y.\
          If just one number is specified, it is taken for both x and y.')
parser.add_argument(
    '--format',
    metavar='DESCRIPTION',
    default='plain',
    help='Specifies format of output file. Can be \'plain\' (matrix of numbers)\
          or \'igor\' (suitable for import into Igor Pro).'
)

args = parser.parse_args()

# Make list of jobs
jobs = []
if args.heights:
    jobs +=  zip(args.heights, ['h' for _i in range(len(args.heights))])
if args.isovalues:
    jobs += zip(args.isovalues, ['i' for _i in range(len(args.isovalues))])
if not jobs:
    print("No isovalues/heights specified. Exiting...")
    sys.exit()    

if args.replicate is not None:
    if len(args.replicate) == 1:
        args.replicate = [ args.replicate, args.replicate]
    elif len(args.replicate) !=2:
        print('Invalid specification of replicas. \
               Please specify --replicate <nx> <ny>.')

# Iterate over supplied cube files
for fname in args.stmcubes:
    print("\nReading {n} ".format(n=fname))
    c = cube.Cube.from_file(fname, read_data=True)

    for v,kind in jobs:
        planefile = None
        header = "STM simulation based on " + fname
        if kind == 'h':
            planefile = "{f}.dz{d}".format(f=fname,d=v)
            header += ", z = {v} [A]".format(v=v)
        elif kind == 'i':
            planefile = "{f}.iso{d}".format(f=fname,d=v)
            header += ", isovalue {v}, zmin {z} [A]".format(v=v, z=args.zmin)
         
        plane = None
        if kind == 'h':
            plane, extent = c.get_plane_above_atoms(v, return_extent=True, 
                              replica=args.replicate)
        elif kind == 'i':
            # todo: still to implement..
            plane, extent = c.get_isosurface_above_atoms(v, zmin=args.zmin,
                    return_extent=True, replica=args.replicate)

        if args.format == 'plain':
            planefile += '.dat'
            print("Writing {} ".format(planefile))
            np.savetxt(planefile, plane, header=header)
        elif args.format == 'igor':
            igorwave = igor.Wave2d(
                    data=plane, 
                    xmin=extent[0],
                    xmax=extent[1],
                    xlabel='x [Angstroms]',
                    ymin=extent[2],
                    ymax=extent[3],
                    ylabel='y [Angstroms]',
            )
            planefile += '.itx'
            print("Writing {} ".format(planefile))
            igorwave.write(planefile)
        else:
            print("Error: Unknown format {}.".format(args.format))

        if args.plot:
            plotfile = planefile + str('.png')
            print("Plotting into {} ".format(plotfile))
            fig = plt.figure()

            vmin = None
            vmax = None
            if args.plotrange:
                vmin = args.plotrange[0]
                vmax = args.plotrange[1]
            #if kind == 'i' and args.plotrange:
            #    vmin = np.max(plane) - args.plotrange
            #    plane = plane - vmin
            #    vmin = 0

            # replicate and resample
            plane, extent = resample(plane, c, rep=args.replicate)

            cax = plt.imshow(plane, extent=extent, 
                             cmap='gray', vmin=vmin, vmax=vmax)
            plt.xlabel('x [$\AA$]')
            plt.ylabel('y [$\AA$]')

            if kind == 'h':
                cbar = fig.colorbar(cax, format='%.1e')
                cbar.set_label('$|\psi|^2$ $[e/a_0^2]$')
            elif kind == 'i':
                cbar = fig.colorbar(cax, format='%.2f')
                cbar.set_label('z [$\AA$]')

            plt.savefig(plotfile, dpi=300)

            resfile = planefile + str('.res')
            print("Saving resampled data used for plotting to {} "\
                    .format(resfile))
            header += "\nDimensions after resampling: {:.3f} < x < {:.3f}, {:.3f} < y < {:.3f} [A]"\
                    .format(extent[0], extent[1], extent[2], extent[3])
            np.savetxt(resfile, plane, header=header)

