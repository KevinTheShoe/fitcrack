#!/usr/bin/python3

# This is XtoHashcat script in Python 3
# Written as part of TARZAN project for identifying digital threads.
# It extracts hash from various files in format appropriate for hashcat
# using several open-source scripts.
# For more info see --help and README

# Authors: Lukas Zobal (izobal@fit.vutbr.cz), Viktor Rucky (xrucky01@stud.fit.vutbr.cz)

# Modifications:
# @date 30.5.2017 Tool created
# @date 17.7.2017 Added StaticHelper class, tool now prints hashType after newline
# @date 28.7.2017 Format numbers in -f are same as hashcat's --hash-type
# @date 06.7.2018 Added check for pkzip and special return code, new RAR/ZIP john2hashcat parsing
# @date 06.10.2020 Added support for PKZIP, SecureZIP, new RAR3-p. Refactorization.
# @date 18.03.2024 Added support for extracting "easy" hashes; see help entry for more info.

# RETURN CODES:
#  * 0 = Everything OK
#  * 1 = General error (file not found/format not recognized/hash not extracted)


import argparse
import os.path
import binascii
import subprocess

from sys import exit, stderr, argv
from typing import List, Optional


class StaticHelper:
    """Class that provides support functions and variables"""

    # ---------- Supported formats ----------
    SupportedFormats = {
        'MS_OFFICE': [9400, 9500, 9600, 9700, 9800],
        'PDF': [10400, 10500, 10600, 10700],
        'RAR': [12500, 13000, 23700, 23800],
        'ZIP': [13600, 17200, 17210, 17225, 17230, 23001, 23002, 23003],
        '7-ZIP': [11600]
    }

    @staticmethod
    def getHashType(hashStr: str, formatId: int, extract_easy_hash:bool) -> str:
        """Chooses the hash mode according to format and extracted hash.

        :param hashStr: Extracted hash, input for hashcat
        :param formatId: Format ID
        :return: hashcat hash mode as a string
        """
        if formatId == 0:
            # MS Office
            if hashStr[1:10].lower() == 'oldoffice':
                if hashStr[11:12] == '0' or hashStr[11:12] == '1':
                    return '9700'       # Office 97-2000 (MD5)
                else:
                    return '9800'       # Office 2003 (SHA1)
            else:
                if hashStr[9:13] == '2007':
                    return '9400'       # Office 2007 (AES + SHA1)
                elif hashStr[9:13] == '2010':
                    return '9500'       # Office 2010 (SHA512)
                else:
                    return '9600'       # Office 2013/16 (100k rounds)
        elif formatId == 1:
            # PDF
            if hashStr[5] == '1':
                return '10400'          # PDF 1.1 - 1.3 (Acrobat 2 - 4)
            elif (hashStr[5] == '2' or
                  hashStr[5] == '3' or
                  hashStr[5] == '4'):
                return '10500'          # PDF 1.4 - 1.6 (Acrobat 5 - 8)
            elif hashStr[5:8] == '5*5':
                return '10600'          # PDF 1.7 Level 3 (Acrobat 9)
            else:
                return '10700'          # PDF 1.7 Level 8 (Acrobat 10 - 11)
        elif formatId == 2:
            # RAR
            if hashStr[1:8].lower() == 'rar3$*0':
                return '12500'          # RAR3-hp
            elif hashStr[1:5].lower() == 'rar5':
                return '13000'          # RAR5
            elif hashStr[1:8].lower() == 'rar3$*1':
                try:
                    method = int(hashStr[-2:])
                    if method == 30:
                        return '23700'  # RAR3-p Uncompressed
                    elif 36 > method > 30:
                        return '23800'  # RAR3-p Compressed
                    else:
                        print(f'Unknown RAR archive (method {method}) "{hashStr[0:9]}..."!', file=stderr)
                        return '-1'
                except ValueError:
                    print(f'Unknown RAR archive (method{hashStr[-2:]}) "{hashStr[0:9]}..."!', file=stderr)
                    return '-1'
            else:
                print(f'Unknown RAR archive "{hashStr[0:9]}..."!', file=stderr)
                return '-1'
        elif formatId == 3:
            # ZIP
            if hashStr[1:5].lower() == 'zip2':
                return '13600'          # Win-Zip
            elif hashStr[1:5].lower() == 'zip3':
                enc_type_pos = hashStr.replace('*', 'X', 2).find('*') + 1
                enc_type = hashStr[enc_type_pos:enc_type_pos + 3]
                if enc_type == '128':
                    return '23001'      # SecureZIP AES-128
                elif enc_type == '192':
                    return '23002'      # SecureZIP AES-192
                elif enc_type == '256':
                    return '23003'      # SecureZIP AES-256
                else:
                    print(f'Unknown AES encryption type "{enc_type}" for SecureZIP!', file=stderr)
                    return '-1'
            elif hashStr[1:6] == 'pkzip':
                hashCount = hashStr[hashStr.find('*') - 1]
                if extract_easy_hash:
                    if int(hashCount) < 3:
                        print(
                            'Warning: You have requested to create an easy hash from a ZIP file that contains fewer than three files. ' +
                            'The output hash is correct and well formed, but Hashcat does not support it and will reject it.', file=stderr)
                    return '17230'      # PKZIP (Mixed Multi-File Checksum-Only)
                if hashCount == '1':
                    compression_type = hashStr[hashStr.replace('*', 'X', 8).find('*') + 1]
                    if compression_type == '8':
                        return '17200'  # PKZIP compressed
                    else:
                        return '17210'  # PKZIP uncompressed
                else:
                    return '17225'      # PKZIP Multifile Mixed
                    
        elif formatId == 4:
            # 7-Zip
            return '11600'              # 7-Zip
        else:
            # Unsupported format
            return '-1'


# ------------ Format class ------------
class Format:
    """Class that represents a single extraction format"""
    def __init__(self, id: int, extensions: List[str], signatures: List[bytes], standardScriptPathAndArgs: List[str], easyScriptPathAndArgs: Optional[List[str]], compiler: str):
        self.id = id
        self.extensions = extensions
        self.signatures = signatures
        self.standardScriptPathAndArgs = standardScriptPathAndArgs
        self.easyScriptPathAndArgs = easyScriptPathAndArgs
        self.compiler = compiler

    def checkSignature(self, signature: bytes) -> bool:
        """Returns True if the signature of parsed file is expected, False otherwise."""
        for sig in self.signatures:
            if signature.startswith(sig):
                return True
        return False

    def checkExtension(self, extension: str) -> bool:
        """Returns True if the extension of parsed file is expected, False otherwise."""
        for ext in self.extensions:
            if extension.lower() == ext:
                return True
        return False

    def checkHash(self, path: str, extract_easy_hash:bool) -> int:
        """Extracts the hash from the file.

        :param path: Path to the file.
        """
        
        if extract_easy_hash and self.easyScriptPathAndArgs is None:
            print('File type of input does not support extraction with easy hash mode.', file=stderr)
            exit(1)
        
        # Call extraction script
        scriptPathAndArgs = self.easyScriptPathAndArgs if extract_easy_hash else self.standardScriptPathAndArgs
        process = subprocess.Popen(scriptPathAndArgs + [path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()

        # Check output
        if len(out) == 0:
            if err is None or len(err) == 0:
                print('Empty output. Is the file encrypted?', file=stderr)
            else:
                print(err.decode('unicode_escape'), file=stderr)
            exit(1)
        else:
            hashStr = out.decode('unicode_escape')

            # ZIP/RAR john2hashcat
            if self.extensions[0] == '.rar' or self.extensions[0] == '.zip':
                hashStr = hashStr[(hashStr.find(':') + 1):]
                colonIndex = hashStr.find(':')

                if colonIndex != -1:
                    hashStr = hashStr[:colonIndex]

            # ZIP often contains path inside hash
            zfileIndex = hashStr.find('ZFILE')
            if zfileIndex != -1:
                suffixIndex = hashStr.find('*', zfileIndex + 6)
                prefixIndex = (hashStr[:(zfileIndex - 2)]).rfind('*')
                hashStr = hashStr[:prefixIndex] + hashStr[suffixIndex:]

            # Print hash '\n' hash-type
            print(hashStr.strip(' \t\n\r') + '\n' + StaticHelper.getHashType(hashStr, self.id, extract_easy_hash))
            return 0


# ---------- Extractor class -----------
class Extractor:
    """Class for extracting a hash from the file."""

    def __init__(self, path: str, extract_easy_hash:bool=False):
        self.path = path
        self.activeFormat = -1
        self.extractEasyHash = extract_easy_hash

        # Create Formats dynamically
        self.extractorFormats = []
        self.extractorFormats.append(Format(0, ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'], [b'd0cf11e0a1b11ae1'], ['scripts/office2hashcat.py'], None, 'python3'))
        self.extractorFormats.append(Format(1, ['.pdf'], [b'25504446'], ['scripts/pdf2hashcat.py'], None,  'python3'))
        self.extractorFormats.append(Format(2, ['.rar'], [b'526172211a07'], ['scripts/rar2john'], None, ''))
        self.extractorFormats.append(Format(3, ['.zip'], [b'504b0304'], ['scripts/zip2john'], ['scripts/zip2john', '-c'], ''))
        self.extractorFormats.append(Format(4, ['.7z'], [b'377abcaf271c'], ['scripts/7z2hashcat.pl'], None, 'perl'))

    def checkFormat(self) -> bool:
        """Attempts to recognize the file format.

        :return: True if format was recognized, False otherwise
        """
        try:
            # Open the file, extract signature and extension
            f = open(self.path, 'rb')
            sig = f.read(20)
            sig = binascii.hexlify(sig)
            ext = os.path.splitext(self.path)[1]
        except OSError:
            print('Failed to open input file.', file=stderr)
            return False

        # Look for a match
        for file_format in self.extractorFormats:
            if file_format.checkSignature(sig) and file_format.checkExtension(ext):
                self.activeFormat = file_format.id
                # Debug
                # print('Identified format: ' + StaticHelper.SupportedFormats[self.activeFormat])
                return True

        print('Format could not be identified, please specify it manually using -f flag.\n'
              'Also, the document might not be encrypted.', file=stderr)
        return False

    def setFormat(self, file_format: int) -> bool:
        """Sets internal object format number according to the user input argument -f.

        :param file_format: Number set by user with the argument -f
        :return: True if the format is supported by this script, False otherwise
        """
        if 9400 <= file_format <= 9800 and file_format % 100 == 0:
            self.activeFormat = 0
        elif 10400 <= file_format <= 10700 and file_format % 100 == 0:
            self.activeFormat = 1
        elif file_format == 12500 or file_format == 13000:
            self.activeFormat = 2
        elif file_format == 13600:
            self.activeFormat = 3
        elif file_format == 11600:
            self.activeFormat = 4
        else:
            print(f'The --hash-type {file_format} is not supported by XtoHashcat.', file=stderr)
            return False

        return True

    def extract(self):
        """Extracts and prints out the hash and hash mode."""
        return self.extractorFormats[self.activeFormat].checkHash(self.path,self.extractEasyHash)


# ---------- Argument parsing ----------
class ArgumentParser(object):
    """Class for argument parsing, using argparse library"""

    def __init__(self):
        pass

    # Help strings
    help_program = 'This program extracts hash from number of formats + prints hashcat --hash-type on the last line'
    help_help = 'Output this message'
    help_file = 'Path to file from which hash is extracted'
    help_format = 'If this argument is set, program will NOT try to determine format automatically but will use supplied format instead. \
Supported set is a sub-set of hashcat supported --hash-types:\n\
\tMicrosoft Office Documents (-f 9400-9800)\n\
\tPDF documents (-f 10400-10700)\n\
\tRAR archive (-f 12500/13000)\n\
\tZIP archive (-f 13600)\n\
\t7-Zip archive (-f 11600)\n\n\
Note: Setting different types of the same document (e.g. 9400 or 9800) makes no difference.'
    help_easy = 'When this option is set, it makes the extractor try to attempt to extract an "easier" version of the hash. \
This is such a hash that is shorter but may lead to false positives when cracking. \
This is useful because regular hashes are sometimes too large to be accepted by Hashcat but the easy variants may be OK. \
If a format does not support extracting and easy hash, then the option does nothing.\
As of now, only ZIP has support for easy hashes.'

    parser = argparse.ArgumentParser(description=help_program, formatter_class=argparse.RawTextHelpFormatter)

    # Load arguments
    def loadArguments(self):
        """Parses program arguments."""
        self.parser.add_argument('filePath', type=str, help=self.help_file)
        self.parser.add_argument('-f', type=int, help=self.help_format)
        self.parser.add_argument('-e', '--easy-hash', action='store_true', help=self.help_easy)

        try:
            args = self.parser.parse_args()
        except argparse.ArgumentError:
            print('See --help for more info.', file=stderr)
            exit(1)

        # Check for duplicates
        if len(argv) > len(set(argv)):
            print('Do not use duplicate arguments.', file=stderr)
            exit(1)

        return args


def main():
    # Argument parsing
    argParser = ArgumentParser()
    args = argParser.loadArguments()

    # Create extractor
    extractor = Extractor(args.filePath,args.easy_hash)

    if args.f or args.f == 0:
        if not extractor.setFormat(args.f):    # set format manually
            exit(1)
    else:
        if not extractor.checkFormat():  # choose format automatically
            exit(1)

    # Try to extract the hash
    return extractor.extract()


if __name__ == "__main__":
    exit(main())
