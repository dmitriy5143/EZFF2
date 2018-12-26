"""Interface to GULP, the General Utility Lattice Program"""
import os
import xtal
import numpy as np

class job:
    """A single GULP job"""

    def __init__(self, verbose=False):
        self.scriptfile = 'in.gulp'
        self.outfile = 'out.gulp'
        self.command = 'gulp'
        self.forcefield = ''
        self.temporary_forcefield = False
        self.structure = None
        self.pbc = False
        self.options = {
            "relax_atoms": False,
            "relax_cell": False,
            "phonon_dispersion": None,
            "phonon_dispersion_from": None,
            "phonon_dispersion_to": None
            }
        self.verbose = verbose
        if verbose:
            print('Created a new GULP job')

    def run(self, command = None, parallel = False, processors = 1, timeout = None):
        """Execute the GULP job"""
        if command is None:
            command = self.command

        if parallel:
            command = "mpirun -np " + str(processors) + " " + command

        system_call_command = command + ' < ' + self.scriptfile + ' > ' + self.outfile + ' 2> ' + self.outfile + '.runerror'

        if timeout is not None:
            system_call_command = 'timeout ' + str(timeout) + ' ' + system_call_command

        if self.verbose:
            print(system_call_command)
        os.system(system_call_command)


    def read_atomic_structure(self,structure_file):
        structure = xtal.AtTraj(verbose=False)

        if ('POSCAR' in structure_file) or ('CONTCAR' in structure_file):
            structure.read_snapshot_vasp(structure_file)

        return structure


    def write_script_file(self, convert_reaxff=None):
        opts = self.options
        script = open(self.scriptfile,'w')
        header_line = ''
        if opts['relax_atoms']:
            header_line += 'optimise '

            if opts['relax_cell']:
                header_line += 'conp '
            else:
                header_line += 'conv '

        if opts['phonon_dispersion'] is not None:
            header_line += 'phonon nofrequency '

        if header_line == '':
            header_line = 'single '

        header_line += 'comp '
        script.write(header_line + '\n')

        script.write('\n')

        if self.pbc:
            script.write('vectors\n')
            script.write(np.array_str(self.structure.box).replace('[','').replace(']','') + '\n')
            script.write('Fractional\n')
            for atom in self.structure.snaplist[0].atomlist:
                positions = atom.element.title() + ' core '
                positions += np.array_str(atom.fract).replace('[','').replace(']','')
                positions += ' 0.0   1.0   0.0   1 1 1 \n'
                script.write(positions)
        else:
            script.write('Cartesian\n')
            for atom in self.structure.snaplist[0].atomlist:
                positions = atom.element.title() + ' core '
                positions += np.array_str(atom.cart).replace('[','').replace(']','')
                positions += ' 0.0   1.0   0.0   1 1 1 \n'
                script.write(positions)
        script.write('\n')


        if convert_reaxff is None:
            with open(self.forcefield,'r') as forcefield_file:
                forcefield = forcefield_file.read()
            for line in forcefield.split('\n'):
                script.write(' '.join(line.split()) + '\n')
        else:
            self.forcefield = convert_reaxff(self.forcefield)
            script.write('library ' + self.forcefield)
        script.write('\n')

        if opts['phonon_dispersion_from'] is not None:
            if opts['phonon_dispersion_to'] is not None:
                script.write('dispersion 1 100 \n')
                script.write(opts['phonon_dispersion_from'] + ' to ' + opts['phonon_dispersion_to']+'\n')
                script.write('output phonon ' + self.outfile)
                script.write('\n')

        script.write('\n')

        script.close()


    def cleanup(self):
        files_to_be_removed = [self.outfile+'.disp', self.outfile+'.dens', self.outfile, self.scriptfile, self.outfile+'.runerror']
        for file in files_to_be_removed:
            if os.path.isfile(file):
                os.remove(file)
        if self.temporary_forcefield:
            if os.path.isfile(self.forcefield):
                os.remove(self.forcefield)



def read_elastic_moduli(outfilename):
    moduli = np.zeros((6,6))
    outfile = open(outfilename,'r')
    for oneline in outfile:
        if 'Elastic Constant Matrix' in oneline:
            dummyline = outfile.readline()
            dummyline = outfile.readline()
            dummyline = outfile.readline()
            dummyline = outfile.readline()
            for i in range(6):
                moduli[i,:] = outfile.readline().strip().split()[1:]
            break
    outfile.close()
    return moduli


def read_lattice_constant(outfilename):
    abc, ang = np.zeros(3), np.zeros(3)
    err_abc, err_ang = np.zeros(3), np.zeros(3)
    outfile = open(outfilename, 'r')
    for oneline in outfile:
        if 'Comparison of initial and final' in oneline:
            dummyline = outfile.readline()
            dummyline = outfile.readline()
            dummyline = outfile.readline()
            dummyline = outfile.readline()
            while True:
                data = outfile.readline().strip().split()
                if data[0] == 'a':
                    abc[0], err_abc[0] = data[2], data[-1]
                elif data[0] == 'b':
                    abc[1], err_abc[1] = data[2], data[-1]
                elif data[0] == 'c':
                    abc[2], err_abc[2] = data[2], data[-1]
                elif data[0] == 'alpha':
                    ang[0], err_ang[0] = data[2], data[-1]
                elif data[0] == 'beta':
                    ang[1], err_ang[1] = data[2], data[-1]
                elif data[0] == 'gamma':
                    ang[2], err_ang[2] = data[2], data[-1]
                elif data[0][0] == '-':
                    break
            break
    outfile.close()
    lattice = {'abc': abc, 'ang': ang, 'err_abc': err_abc, 'err_ang': err_ang}
    return lattice

def read_energy(outfilename):
    outfile = open(outfilename, 'r')
    for line in outfile:
        if 'Total lattice energy' in line:
            if line.strip().split()[-1] == 'eV':
                energy_in_eV = float(line.strip().split()[-2])
    return energy_in_eV
    outfile.close()

def read_phonon_dispersion(phonon_dispersion_file, units='cm-1'):
    pbs = []
    freq_conversion = {'cm-1': 0.0299792453684314, 'THz': 1, 'eV': 241.79893, 'meV': 0.24180}
    dispersion = open(phonon_dispersion_file, 'r')
    for line in dispersion:
        if not line.strip().startswith('#'):
            _, freq = line.strip().split()
            pbs.append(float(freq))
    dispersion.close()
    num_bands = int(len(pbs)/100)
    pbs = np.array(pbs).reshape((100,num_bands)).T
    pbs *= freq_conversion[units]
    return pbs
