from __future__ import print_function
from collections import defaultdict
import os
import sys
import shutil

from elftools.elf.elffile import ELFFile
from shutil import copyfile, ignore_patterns

fn_list = []

def do_copy_file(src, dst):
    # check source file
    if not os.path.exists(src):
        return

    path = os.path.dirname(dst)
    # mkdir if path not exist
    if not os.path.exists(path):
        os.makedirs(path)

    shutil.copy2(src, dst)

def splitall(loc):
    """
    Return a list of the path components in loc. (Used by relpath_).

    The first item in the list will be  either ``os.curdir``, ``os.pardir``, empty,
    or the root directory of loc (for example, ``/`` or ``C:\\).

    The other items in the list will be strings.

    Adapted from *path.py* by Jason Orendorff.
    """
    parts = []
    while loc != os.curdir and loc != os.pardir:
        prev = loc
        loc, child = os.path.split(prev)
        if loc == prev:
            break
        parts.append(child)
    parts.append(loc)
    parts.reverse()
    return parts

def _make_path_relative(origin, dest):
    """
    Return the relative path between origin and dest.

    If it's not possible return dest.


    If they are identical return ``os.curdir``

    Adapted from `path.py <http://www.jorendorff.com/articles/python/path/>`_ by Jason Orendorff.
    """
    origin = os.path.abspath(origin).replace('\\', '/')
    dest = os.path.abspath(dest).replace('\\', '/')
    #
    orig_list = splitall(os.path.normcase(origin))
    # Don't normcase dest!  We want to preserve the case.
    dest_list = splitall(dest)
    #
    if orig_list[0] != os.path.normcase(dest_list[0]):
        # Can't get here from there.
        return dest
    #
    # Find the location where the two paths start to differ.
    i = 0
    for start_seg, dest_seg in zip(orig_list, dest_list):
        if start_seg != os.path.normcase(dest_seg):
            break
        i += 1
    #
    # Now i is the point where the two paths diverge.
    # Need a certain number of "os.pardir"s to work up
    # from the origin to the point of divergence.
    segments = [os.pardir] * (len(orig_list) - i)
    # Need to add the diverging part of dest_list.
    segments += dest_list[i:]
    if len(segments) == 0:
        # If they happen to be identical, use os.curdir.
        return os.curdir
    else:
        # return os.path.join(*segments).replace('\\', '/')
        return os.path.join(*segments)

def process_file(filename):
    print('Processing file:', filename)
    with open(filename, 'rb') as f:
        elffile = ELFFile(f)

        if not elffile.has_dwarf_info():
            print('  file has no DWARF info')
            return

        dwarfinfo = elffile.get_dwarf_info()
        for CU in dwarfinfo.iter_CUs():
            # print('  Found a compile unit at offset %s, length %s' % (CU.cu_offset, CU['unit_length']))

            # Every compilation unit in the DWARF information may or may not
            # have a corresponding line program in .debug_line.
            line_program = dwarfinfo.line_program_for_CU(CU)
            if line_program is None:
                print('  DWARF info is missing a line program for this CU')
                continue

            # Print a reverse mapping of filename -> #entries
            line_entry_mapping(os.path.dirname(filename), line_program)

def line_entry_mapping(path, line_program):
    filename_map = defaultdict(int)

    # The line program, when decoded, returns a list of line program
    # entries. Each entry contains a state, which we'll use to build
    # a reverse mapping of filename -> #entries.
    lp_entries = line_program.get_entries()
    for lpe in lp_entries:
        # We skip LPEs that don't have an associated file.
        # This can happen if instructions in the compiled binary
        # don't correspond directly to any original source file.
        if not lpe.state or lpe.state.file == 0:
            continue
        filename = lpe_filename(line_program, lpe.state.file)
        filename_map[filename] += 1

    for filename, lpe_count in filename_map.items():
        filename = os.path.abspath(os.path.join(path, filename))
        if filename not in fn_list:
            # print("add ", filename)
            fn_list.append(filename)

        #print("    filename=%s -> %d entries" % (filename, lpe_count))

def lpe_filename(line_program, file_index):
    # Retrieving the filename associated with a line program entry
    # involves two levels of indirection: we take the file index from
    # the LPE to grab the file_entry from the line program header,
    # then take the directory index from the file_entry to grab the
    # directory name from the line program header. Finally, we
    # join the (base) filename from the file_entry to the directory
    # name to get the absolute filename.
    lp_header = line_program.header
    file_entries = lp_header["file_entry"]

    # File and directory indices are 1-indexed.
    file_entry = file_entries[file_index - 1]
    dir_index = file_entry["dir_index"]

    # A dir_index of 0 indicates that no absolute directory was recorded during
    # compilation; return just the basename.
    if dir_index == 0:
        return file_entry.name.decode()

    directory = lp_header["include_directory"][dir_index - 1]
    return os.path.join(directory, file_entry.name).decode()

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: %s elf dest [proj_folder]' % sys.argv[0])
        exit(0)

    if len(sys.argv) > 1:
        process_file(sys.argv[1])

        dest = sys.argv[2]
        proj = os.path.dirname(sys.argv[1])
        if len(sys.argv) > 3:
            proj = sys.argv[3]

        relative_fn_list = []
        # print(fn_list)
        for item in fn_list:
            relative_item = _make_path_relative(proj, item)

            if not relative_item.startswith('..'):
                print('%s => %s' %(item, os.path.join(dest, relative_item)))
                do_copy_file(item, os.path.join(dest, relative_item))

                relative_fn_list.append(relative_item)
            else:
                print("skip file: ", relative_item)
                # print("abspath  : ", item)
