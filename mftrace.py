#!@PYTHON@

import string
import os
import getopt
import sys
import re
import tempfile
import shutil

prefix = '@prefix@'
bindir = '@bindir@'
datadir = '@datadir@'
libdir = '@libdir@'
exec_prefix = '@exec_prefix@'

def interpolate (str):
	str = string.replace (str, '{', '(')
	str = string.replace (str, '}', ')s')
	str = string.replace (str, '$', '%')
	return str

if prefix != '@' + 'prefix@':
	exec_prefix = interpolate (exec_prefix) % vars ()
	bindir = interpolate (bindir) % vars ()
	datadir = os.path.join (interpolate (datadir) % vars (), 'mftrace')
	libdir = interpolate (libdir) % vars ()

# run from textrace-source dir.
exit_value = 0
simplify_p = 0
verbose_p = 0
dos_kpath_p = 0
keep_trying_p = 0
backend_options = ''
formats = []
read_afm_p = 1

# You can take this higher, but then rounding errors will have
# nasty side effects.
# Used as reciprocal grid size
potrace_scale = 1.0
round_to_int = 1

magnification = 1000.0
program_name = 'mftrace'
temp_dir = os.path.join (os.getcwd (), program_name + '.dir')
gf_fontname = ''

keep_temp_dir_p = 0
program_version = '@VERSION@'
origdir = os.getcwd ()

coding_dict = {

	# from TeTeX
	'TeX typewriter text': '09fbbfac.enc', # cmtt10
	'TeX math symbols':'10037936.enc ', # cmbsy
	'ASCII caps and digits':'1b6d048e', # cminch
	'TeX math italic': 'aae443f0.enc ', # cmmi10
	'TeX extended ASCII':'d9b29452.enc',
	'TeX text': 'f7b6d320.enc',
	'TeX text without f-ligatures': '0ef0afca.enc',

	'Extended TeX Font Encoding - Latin': 'tex256.enc',

	# LilyPond.
	'fetaBraces': 'feta-braces-a.enc',
	'fetaNumber': 'feta-nummer10.enc',
	'fetaMusic': 'feta20.enc',
	'parmesanMusic': 'parmesan20.enc',
	}


if datadir == '@' + "datadir" + "@":
	datadir = os.getcwd ()

sys.path.append (datadir)

import afm
import tfm

errorport = sys.stderr

################################################################
# lilylib.py -- options and stuff
#
# source file of the GNU LilyPond music typesetter

try:
	import gettext
	gettext.bindtextdomain ('mftrace', localedir)
	gettext.textdomain ('mftrace')
	_ = gettext.gettext
except:
	def _ (s):
		return s

def identify (port):
	port.write ('%s %s\n' % (program_name, program_version))

def warranty ():
	identify (sys.stdout)
	sys.stdout.write ('\n')
	sys.stdout.write (_ ('Copyright (c) %s by' % ' 2001--2004'))
	sys.stdout.write ('\n')
	sys.stdout.write ('  Han-Wen Nienhuys')
	sys.stdout.write ('  Jan Nieuwenhuizen')
	sys.stdout.write ('\n')
	sys.stdout.write (_ (r'''
Distributed under terms of the GNU General Public License.  It comes with
NO WARRANTY.'''))
	sys.stdout.write ('\n')

def progress (s):
	errorport.write (s)

def warning (s):
	errorport.write (_ ("warning: ") + s)

def error (s):
	'''Report the error S.  Exit by raising an exception.  Please
	do not abuse by trying to catch this error.  If you do not want
	a stack trace, write to the output directly.

	RETURN VALUE

	None

	'''

	errorport.write (_ ("error: ") + s + '\n')
	raise _ ("Exiting ... ")

def getopt_args (opts):
	'''Construct arguments (LONG, SHORT) for getopt from list of options.'''
	short = ''
	long = []
	for o in opts:
		if o[1]:
			short = short + o[1]
			if o[0]:
				short = short + ':'
		if o[2]:
			lst = o[2]
			if o[0]:
				lst = lst + '='
			long.append (lst)
	return (short, long)

def option_help_str (o):
	'''Transform one option description (4-tuple) into neatly formatted string'''
	sh = '  '
	if o[1]:
		sh = '-%s' % o[1]

	sep = ' '
	if o[1] and o[2]:
		sep = ','

	long = ''
	if o[2]:
		long = '--%s' % o[2]

	arg = ''
	if o[0]:
		if o[2]:
			arg = '='
		arg = arg + o[0]
	return '  ' + sh + sep + long + arg

def options_help_str (opts):
	'''Convert a list of options into a neatly formatted string'''
	w = 0
	strs = []
	helps = []

	for o in opts:
		s = option_help_str (o)
		strs.append ((s, o[3]))
		if len (s) > w:
			w = len (s)

	str = ''
	for s in strs:
		str = str + '%s%s%s\n' % (s[0], ' ' * (w - len (s[0]) + 3), s[1])
	return str

def help ():
	ls = [(_ ("Usage: %s [OPTION]... FILE...") % program_name),
		('\n\n'),
		(help_summary),
		('\n\n'),
		(_ ("Options:")),
		('\n'),
		(options_help_str (option_definitions)),
		('\n\n'),
		(_ ("Report bugs to %s") % 'hanwen@cs.uu.nl'),
		('\n')]
	map (sys.stdout.write, ls)

def setup_temp ():
	"""
	Create a temporary directory, and return its name.
	"""
	global temp_dir
	if not keep_temp_dir_p:
		temp_dir = tempfile.mktemp (program_name)
	try:
		os.mkdir (temp_dir, 0700)
	except OSError:
		pass

	return temp_dir

def popen (cmd, mode = 'r', ignore_error = 0):
	if verbose_p:
		progress (_ ("Opening pipe `%s\'") % cmd)
	pipe = os.popen (cmd, mode)
	if verbose_p:
		progress ('\n')
	return pipe

def system (cmd, ignore_error = 0):
	"""Run CMD. If IGNORE_ERROR is set, don't complain when CMD returns non zero.

	RETURN VALUE

	Exit status of CMD
	"""

	if verbose_p:
		progress (_ ("Invoking `%s\'\n") % cmd)
	st = os.system (cmd)
	if st:
		name = re.match ('[ \t]*([^ \t]*)', cmd).group (1)
		msg = name + ': ' + _ ("command exited with value %d") % st
		if ignore_error:
			warning (msg + ' ' + _ ("(ignored)") + ' ')
		else:
			error (msg)
	if verbose_p:
		progress ('\n')
	return st

def cleanup_temp ():
	if not keep_temp_dir_p:
		if verbose_p:
			progress (_ ("Cleaning %s...") % temp_dir)
		shutil.rmtree (temp_dir)


def strip_extension (f, ext):
	(p, e) = os.path.splitext (f)
	if e == ext:
		e = ''
	return p + e


################################################################
# END Library


help_summary = _ ("""Generate Type1 or TrueType font from Metafont source.

Example:

   mftrace cmr10""")

option_definitions = [
	('', 'h', 'help', _ ("This help")),
	('', 'k', 'keep', _ ("Keep all output in directory %s.dir") % program_name),
	('MAG', '', 'magnification', _ ("Set magnification for MF to MAG (default: 1000)")),
	('', 'V', 'verbose', _ ("Verbose")),
	('', 'v', 'version', _ ("Print version number")),
	('FMT1,FMT2,etc', 'f', 'formats', _ ("Which formats to generate (choices: AFM, PFA, PFB, TTF, SVG)")),
	('', '', 'simplify', _ ("Simplify using fontforge")),
	('FILE', '', 'gffile', _ ("Use gf FILE instead of running Metafont")),
	('DIR', 'I', 'include', _ ("Add to path for searching files")),
	('LIST', '', 'glyphs', _ ('Process only these glyphs.  LIST is comma separated')),
	('FILE', '', 'tfmfile', _ ("Use FILE for the TFM file")),
	('FILE', 'e', 'encoding', _ ("Use encoding file FILE")),
	('', '', 'keep-trying', _ ("Don't stop if tracing fails")),
	('', 'w', 'warranty', _ ("show warranty and copyright")),
	('', '', 'dos-kpath', _ ("try to use Miktex kpsewhich")),
	('', '', 'potrace', _ ("Use potrace")),
	('', '', 'autotrace', _ ("Use autotrace")),
	('', '', 'no-afm', _("Don't read AFM file")),
	('', '', 'noround', _ ("Do not round coordinates of control points \n                             to integer values (use with --grid)")),
	('GRID', '', 'grid', _ ("Set reciprocal grid size in em units"))
	]


include_dirs = [origdir]
def find_file (nm):
	for d in include_dirs:
		p = os.path.join (d, nm)
		try:
			f = open (p)
			return p
		except IOError:
			pass

	p = popen ('kpsewhich %s' % nm).read ()[:-1]

	# urg. Did I do this ?
	if dos_kpath_p:
		orig = p
		def func (m):
			return string.lower (m.group (1))
		p = string.lower (p)
		p = re.sub ('^([a-z]):', '/cygdrive/\\1', p)
		p = re.sub ('\\\\', '/', p)
		sys.stderr.write ("Got `%s' from kpsewhich, using `%s'\n" % (orig, p))
	return p


################################################################
# TRACING.
################################################################

def autotrace_command (fn, opts):
	opts = " " + opts + " --background-color=FFFFFF --output-format=eps --input-format=pbm "
	return trace_binary + opts + backend_options \
	       + " --output-file=char.eps %s " % fn

def potrace_command (fn, opts):
	return trace_binary + opts \
		+ ' -u %d ' % potrace_scale \
		+ backend_options \
		+ " -q -c --eps --output=char.eps %s " % (fn)

trace_command = None
trace_binary = ''
path_to_type1_ops = None

def trace_one (pbmfile, id):
	"""
	Run tracer, do error handling
	"""

	status = system (trace_command (pbmfile, ''), 1)

	if status == 2:
		sys.stderr.write ("\nUser interrupt. Exiting\n")
		sys.exit (2)

	if status == 0 and keep_temp_dir_p:
		shutil.copy2 (pbmfile, '%s.pbm' % id)
		shutil.copy2 ('char.eps', '%s.eps' % id)

	if status != 0:
		error_file = os.path.join (origdir, 'trace-bug-%s.pbm' % id)
		shutil.copy2 (pbmfile, error_file)
		msg = """Trace failed on bitmap.  Bitmap left in `%s\'
Failed command was:

	%s

Please submit a bugreport to %s development.""" \
		% (error_file, trace_command (error_file, ''), trace_binary)

		if keep_trying_p:
			warning (msg)
			sys.stderr.write ("\nContinuing trace...\n")
			exit_value = 1
		else:
			msg = msg + '\nRun mftrace with --keep-trying to produce a font anyway\n'
			error (msg)
	else:
		return 1

	if status != 0:
		warning ("Failed, skipping character.\n")
		return 0
	else:
		return 1

def make_pbm (filename, outname, char_number):
	""" Extract bitmap from the PK file FILENAME (absolute) using `gf2pbm'.
	Return FALSE if the glyph is not valid.
	"""

	command = "%s/gf2pbm -n %d -o %s %s" % (bindir, char_number, outname, filename)
	status = system (command, ignore_error = 1)
	return (status == 0)

def read_encoding (file):
	sys.stderr.write (_ ("Using encoding file: `%s'\n") % file)

	str = open (file).read ()
	str = re.sub ("%.*", '', str)
	str = re.sub ("[\n\t \f]+", ' ', str)
	m = re.search ('/([^ ]+) \[([^\]]+)\] def', str)
	if not m:
		raise 'Encoding file invalid.'

	name = m.group (1)
	cod = m.group (2)
	cod = re.sub ('[ /]+', ' ', cod)
	cods = string.split (cod)

	return (name, cods)

def zip_to_pairs (as):
	r = []
	while as:
		r.append ((as[0], as[1]))
		as = as[2:]
	return r

def unzip_pairs (tups):
	lst = []
	while tups:
		lst = lst + list (tups[0])
		tups = tups[1:]
	return lst

def autotrace_path_to_type1_ops (at_file, bitmap_metrics, tfm_wid):
	inv_scale = 1000.0 / magnification

	(size_y, size_x, off_x, off_y) = map (lambda m, s = inv_scale: m * s,
					      bitmap_metrics)
	ls = open (at_file).readlines ()
	bbox = (10000, 10000, -10000, -10000)

	while ls and ls[0] != '*u\n':
		ls = ls[1:]

	if ls == []:
		return (bbox, '')

	ls = ls[1:]

	commands = []


	while ls[0] != '*U\n':
		ell = ls[0]
		ls = ls[1:]

		toks = string.split (ell)

		if len (toks) < 1:
			continue
		cmd = toks[-1]
		args = map (lambda m, s = inv_scale: s * string.atof (m),
			    toks[:-1])
		if round_to_int:
			args = zip_to_pairs (map (round, args))
		else:
			args = zip_to_pairs (args)
		commands.append ((cmd, args))

	expand = {
		'l': 'rlineto',
		'm': 'rmoveto',
		'c': 'rrcurveto',
		'f': 'closepath',
		}

	cx = 0
	cy = size_y - off_y - inv_scale

	# t1asm seems to fuck up when using sbw. Oh well.
	t1_outline =  '  %d %d hsbw\n' % (- off_x, tfm_wid)
	bbox = (10000, 10000, -10000, -10000)

	for (c, args) in commands:

		na = []
		for a in args:
			(nx, ny) = a
			if c == 'l' or c == 'c':
				bbox = update_bbox_with_point (bbox, a)

			na.append ((nx - cx, ny - cy))
			(cx, cy) = (nx, ny)

		a = na
		c = expand[c]
		if round_to_int:
			a = map (lambda x: '%d' % int (round (x)),
				 unzip_pairs (a))
		else:
			a = map (lambda x: '%d %d div' \
				 % (int (round (x * potrace_scale/inv_scale)),
				    int (round (potrace_scale/inv_scale))),
				 unzip_pairs (a))

		t1_outline = t1_outline + ' %s %s\n' % (string.join (a), c)

	t1_outline = t1_outline + ' endchar '
	t1_outline = '{\n %s } |- \n' % t1_outline

	return (bbox, t1_outline)

# FIXME: Cut and paste programming
def potrace_path_to_type1_ops (at_file, bitmap_metrics, tfm_wid):
	inv_scale = 1000.0 / magnification

	(size_y, size_x, off_x, off_y) = map (lambda m,
					      s = inv_scale: m * s,
					      bitmap_metrics)
	ls = open (at_file).readlines ()
	bbox =  (10000, 10000, -10000, -10000)

	while ls and ls[0] != '0 setgray\n':
		ls = ls[1:]

	if ls == []:
		return (bbox, '')
	ls = ls[1:]
	commands = []

	while ls and ls[0] != 'grestore\n':
		ell = ls[0]
		ls = ls[1:]

		if ell == 'fill\n':
			continue

		toks = string.split (ell)

		if len (toks) < 1:
			continue
		cmd = toks[-1]
		args = map (lambda m, s = inv_scale: s * string.atof (m),
			    toks[:-1])
		args = zip_to_pairs (args)
		commands.append ((cmd, args))

	# t1asm seems to fuck up when using sbw. Oh well.
	t1_outline = '  %d %d hsbw\n' % (- off_x, tfm_wid)
	bbox =  (10000, 10000, -10000, -10000)

	# Type1 fonts have relative coordinates (doubly relative for
	# rrcurveto), so must convert moveto and rcurveto.

	z = (0.0, size_y - off_y - 1.0)
	nc = []
	for (c, args) in commands:
		args = map (lambda x: (x[0] * (1.0 / potrace_scale),
				       x[1] * (1.0 / potrace_scale)), args)

		if c == 'moveto':
			args = [(args[0][0] - z[0], args[0][1] - z[1])]

		zs = []
		for a in args:
			lz = (z[0] + a[0], z[1] + a[1])
			bbox = update_bbox_with_point (bbox, lz)
			zs.append (lz)

		if round_to_int:
			last_discr_z = (int (round (z[0])), int (round (z[1])))
		else:
			last_discr_z = (z[0], z[1])
		args = []
		for a in zs:
			if round_to_int:
				a = (int (round (a[0])), int (round (a[1])))
			else:
				a = (a[0], a[1])
			args.append ((a[0] - last_discr_z[0],
				       a[1] - last_discr_z[1]))

			last_discr_z = a

		if zs:
			z = zs[-1]
		c = { 'rcurveto': 'rrcurveto',
		      'moveto': 'rmoveto',
		      'closepath': 'closepath',
		      'rlineto': 'rlineto'}[c]

		if c == 'rmoveto':
			t1_outline += ' closepath '

		if round_to_int:
			args = map (lambda x: '%d' % int (round (x)),
				    unzip_pairs (args))
		else:
			args = map (lambda x: '%d %d div' \
				    % (int (round (x*potrace_scale/inv_scale)),
				       int (round (potrace_scale/inv_scale))),
				    unzip_pairs (args))

		t1_outline = t1_outline + '  %s %s\n' % (string.join (args), c)

	t1_outline = t1_outline + ' endchar '
	t1_outline = '{\n %s } |- \n' % t1_outline

	return (bbox, t1_outline)

def read_gf_dims (name, c):
	str = popen ('%s/gf2pbm -n %d -s %s' % (bindir, c, name)).read ()
	m = re.search ('size: ([0-9]+)+x([0-9]+), offset: \(([0-9-]+),([0-9-]+)\)', str)

	return tuple (map (string.atoi, m.groups ()))

def trace_font (fontname, gf_file, metric, glyphs, encoding,
		magnification, fontinfo):
	t1os = []
	font_bbox = (10000, 10000, -10000, -10000)

	progress (_ ("Tracing bitmaps... "))

	eps_lines = []

	# for single glyph testing.
	# glyphs = []
	first_p = 1
	global verbose_p
	vp = verbose_p
	for a in glyphs:
		valid = metric.has_char (a)
		if not valid:
			continue

		valid = make_pbm (gf_file, 'char.pbm', a)
		if not valid:
			continue

		(w, h, xo, yo) = read_gf_dims (gf_file, a)

		if not verbose_p:
			sys.stderr.write ('[%d' % a)
			sys.stderr.flush ()

		# this wants the id, not the filename.
		success = trace_one ("char.pbm", '%s-%d' % (gf_fontname, a))
		if not success:
			sys.stderr.write ("(skipping character)]")
			sys.stderr.flush ()
			continue

		if not verbose_p:
			sys.stderr.write (']')
			sys.stderr.flush ()
		metric_width = metric.get_char (a).width
		tw = int (round (metric_width / metric.design_size * 1000))
		(bbox, t1o) = path_to_type1_ops ("char.eps", (h, w, xo, yo),
						 tw)

		if t1o == '':
			continue

		font_bbox = update_bbox_with_bbox (font_bbox, bbox)

		t1os.append ('/%s %s ' % (encoding[a], t1o))

		if first_p:
			verbose_p = 0

	verbose_p = vp
	progress ('\n')
	to_type1 (t1os, font_bbox, fontname, encoding, magnification, fontinfo )

def ps_encode_encoding (encoding):
	str = ' %d array\n0 1 %d {1 index exch /.notdef put} for\n' \
	      % (len (encoding), len (encoding)-1)

	for i in range (0, len (encoding)):
		str = str + 'dup %d /%s put\n' % (i, encoding[i])

	return str


def gen_unique_id (dict):
	nm = 'FullName'
	return 4000000 + (hash (nm) % 1000000)

def to_type1 (outlines, bbox, fontname, encoding, magnification, fontinfo):
	"""
	Fill in the header template for the font, append charstrings,
	and shove result through t1asm
	"""
	template = r"""%%!PS-AdobeFont-1.0: %(FontName)s %(VVV)s.%(WWW)s
13 dict begin
/FontInfo 16 dict dup begin
/version (%(VVV)s.%(WWW)s) readonly def
/Notice (%(Notice)s) readonly def
/FullName (%(FullName)s) readonly def
/FamilyName (%(FamilyName)s) readonly def
/Weight (%(Weight)s) readonly def
/ItalicAngle %(ItalicAngle)s def
/isFixedPitch %(isFixedPitch)s def
/UnderlinePosition %(UnderlinePosition)s def
/UnderlineThickness %(UnderlineThickness)s def
end readonly def
/FontName /%(FontName)s def
/FontType 1 def
/PaintType 0 def
/FontMatrix [%(xrevscale)f 0 0 %(yrevscale)f 0 0] readonly def
/FontBBox {%(llx)d %(lly)d %(urx)d %(ury)d} readonly def
/Encoding %(Encoding)s readonly def
currentdict end
currentfile eexec
dup /Private 20 dict dup begin
/-|{string currentfile exch readstring pop}executeonly def
/|-{noaccess def}executeonly def
/|{noaccess put}executeonly def
/lenIV 4 def
/password 5839 def
/MinFeature {16 16} |-
/BlueValues [] |-
/OtherSubrs [ {} {} {} {} ] |-
/ForceBold false def
/Subrs 1 array
dup 0 { return } |
|-
2 index
/CharStrings %(CharStringsLen)d dict dup begin
%(CharStrings)s


 /.notdef { 0 0 hsbw endchar } |-
end
end
readonly put
noaccess put
dup/FontName get exch definefont
pop mark currentfile closefile
cleartomark
"""
## apparently, some fonts end the file with cleartomark.  Don't know why.

	copied_fields = ['FontName', 'FamilyName', 'FullName', 'DesignSize',
			 'ItalicAngle', 'isFixedPitch', 'Weight']

	vars = {
		'VVV': '001',
		'WWW': '001',
		'Notice': 'Generated from MetaFont bitmap by mftrace %s, http://www.cs.uu.nl/~hanwen/mftrace/ ' % program_version,
		'UnderlinePosition': '-100',
		'UnderlineThickness': '50',
		'xrevscale': 1.0/1000.0,
		'yrevscale': 1.0/1000.0,
		'llx': bbox[0],
		'lly': bbox[1],
		'urx': bbox[2],
		'ury': bbox[3],
		'Encoding': ps_encode_encoding (encoding),

		# need one extra entry for .notdef
		'CharStringsLen': len (outlines) + 1,
		'CharStrings': string.join (outlines),
		'CharBBox': '0 0 0 0',
	}

	for k in copied_fields:
		vars[k] = fontinfo[k]

	open ('mftrace.t1asm', 'w').write (template % vars)

	opt = ''

	outname = fontname + '.pfa'

	rawname = outname + '.raw'
	progress (_ ("Assembling raw font to `%s'... ") % rawname)
	system ('t1asm --pfa mftrace.t1asm %s' % rawname)
	progress ('\n')

def update_bbox_with_point (bbox, pt):
	(llx, lly, urx, ury) = bbox
	llx = min (pt[0], llx)
	lly = min (pt[1], lly)
	urx = max (pt[0], urx)
	ury = max (pt[1], ury)

	return 	(llx, lly, urx, ury)

def update_bbox_with_bbox (bb, dims):
	(llx, lly, urx, ury) = bb
	llx = min (llx, dims[0])
	lly = min (lly, dims[1])
	urx = max (urx, dims[2])
	ury = max (ury, dims[3])

	return (llx, lly, urx, ury)

def get_binary (name):
	search_path = string.split (os.environ['PATH'], ':')
	for p in search_path:
		nm = os.path.join (p, name)
		if os.path.exists (nm):
			return nm

	return ''

def get_fontforge_command ():
	fontforge_cmd = ''
	for ff in ['fontforge', 'pfaedit']:
		if get_binary(ff):
			fontforge_cmd = ff

	stat = 1
	if fontforge_cmd:
		stat = system ("%s -usage > pfv 2>&1 " % fontforge_cmd,
			       ignore_error = 1)

		if stat != 0:
			warning ("Command `%s -usage' failed.  Cannot simplify or convert to TTF.\n" % fontforge_cmd)

	if fontforge_cmd == 'pfaedit' \
	   and re.search ("-script", open ('pfv').read ()) == None:
		warning ("pfaedit does not support -script.  Install 020215 or later.\nCannot simplify or convert to TTF.\n")
		return ''
	return fontforge_cmd

def make_outputs (fontname, formats):
	"""
	run pfaedit to convert to other formats
	"""

	ff_command = get_fontforge_command ()
	if not ff_command:
		shutil.copy2 (fontname + '.pfa.raw',
			      fontname + '.pfa')
		return 0

	# not used?
	if round_to_int :
		round_cmd = 'RoundToInt();\n'

	generate_cmds = ''
	for f in formats:
		generate_cmds += 'Generate("%s");' % (fontname + '.' + f)

	simplify_cmd = ''
	if simplify_p:
		simplify_cmd ='''SelectAll ();
SelectAll ();
AddExtrema();
Simplify ();
AutoHint ();'''

	open ('to-ttf.pe', 'w').write ('''#!/usr/bin/env %(ff_command)s
Open ($1);
MergeKern($2);
%(round_cmd)s
%(simplify_cmd)s
%(generate_cmds)s
Quit (0);
''' % vars())

	system ("%s -script to-ttf.pe %s %s" % (ff_command,
						(fontname+ '.pfa.raw'), tfmfile))

def getenv (var, default):
	if os.environ.has_key (var):
		return os.environ[var]
	else:
		return default

def gen_pixel_font (filename, metric, magnification):
	"""
	Generate a GF file for FILENAME, such that `magnification'*mfscale
	(default 1000 * 1.0) pixels fit on the designsize.
	"""
	base_dpi = 1200

	size = metric.design_size

	size_points = size * 1/72.27 * base_dpi

	mag = magnification / size_points

	prod = mag * base_dpi
	try:
		f = open ('%s.%dgf' % (filename, prod))
	except IOError:
		os.environ['KPSE_DOT'] = '%s:' % origdir

		os.environ['MFINPUTS'] = '%s:%s' % (origdir,
						    getenv ('MFINPUTS', ''))
		os.environ['TFMFONTS'] = '%s:%s' % (origdir,
						    getenv ('TFMINPUTS', ''))

		# FIXME: we should not change to another (tmp) dir?
		# or else make all relavitive dirs in paths absolute.
		def abs_dir (x, dir):
			if x and os.path.abspath (x) != x:
				return os.path.join (dir, x)
			return x

		def abs_path (path, dir):
			# Python's ABSPATH means ABSDIR
			dir = os.path.abspath (dir)
			return string.join (map (lambda x: abs_dir (x, dir),
						 string.split (path,
							       os.pathsep)),
					    os.pathsep)

		os.environ['MFINPUTS'] = abs_path (os.environ['MFINPUTS'],
						   origdir)
		os.environ['TFMFONTS'] = abs_path (os.environ['TFMFONTS'],
						   origdir)

		progress (_ ("Running Metafont..."))

		cmdstr = r"mf '\mode:=lexmarks; mag:=%f; nonstopmode; input %s'" %  (mag, filename)
		if not verbose_p:
			cmdstr = cmdstr + ' 1>/dev/null 2>/dev/null'
		st = system (cmdstr, ignore_error = 1)
		progress ('\n')

		logfile = '%s.log' % filename
		log = ''
		if os.path.exists (logfile):
			log = open (logfile).read ()

		if st:
			sys.stderr.write ('\n\nMetafont failed.  Excerpt from the log file: \n\n*****')
			m = re.search ("\n!", log)
			start = m.start (0)
			short_log = log[start:start+200]
			sys.stderr.write (short_log)
			sys.stderr.write ('\n*****\n')
			if re.search ('Arithmetic overflow', log):
				sys.stderr.write ("""

Apparently, some numbers overflowed.  Try using --magnification with a
lower number.  (Current magnification: %d)
""" % magnification)

			sys.exit (1)
		m = re.search ('Output written on %s.([0-9]+)gf' % re.escape (filename), log)
		prod = string.atoi (m.group (1))

	return "%s.%d" % (filename, prod)

(sh, long) = getopt_args (option_definitions)
try:
	(options, files) = getopt.getopt (sys.argv[1:], sh, long)
except getopt.error, s:
	errorport.write ('\n')
	errorport.write (_ ("error: ") + _ ("getopt says: `%s\'" % s))
	errorport.write ('\n')
	errorport.write ('\n')
	help ()
	sys.exit (2)

def derive_font_name (family, fullname):
	fullname = re.sub (family, '', fullname)
	family = re.sub (' ',  '', family)
	fullname = re.sub ('Oldstyle Figures', 'OsF', fullname)
	fullname = re.sub ('Small Caps', 'SC', fullname)
	fullname = re.sub ('[Mm]edium', '', fullname)
	fullname = re.sub ('[^A-Za-z0-9]', '', fullname)
	return '%s-%s' % (family, fullname)
	
def cm_guess_font_info (filename, fontinfo):
	# urg.
	filename = re.sub ("cm(.*)tt", r"cmtt\1", filename)
	m = re.search ("([0-9]+)$", filename)
	design_size = ''
	if m:
		design_size = string.atoi (m.group (1))
		fontinfo['DesignSize'] = design_size

	prefixes = [("cmtt", "Computer Modern Typewriter"),
		    ("cmvtt", "Computer Modern Variable Width Typewriter"),
		    ("cmss", "Computer Modern Sans"),
		    ("cm", "Computer Modern")]

	family = ''
 	for (k, v) in prefixes:
		if re.search (k, filename):
			family = v
			if k == 'cmtt':
				fontinfo['isFixedPitch'] = 'true'
			filename = re.sub (k, '', filename)
			break

	# shapes
	prefixes = [("r", "Roman"),
		    ("mi", "Math italic"),
		    ("u", "Unslanted italic"),
		    ("sl", "Oblique"),
		    ("csc", "Small Caps"),
		    ("ex", "Math extension"),
		    ("ti", "Text italic"),
		    ("i", "Italic")]
	shape = ''
 	for (k, v) in prefixes:
		if re.search (k, filename):
			shape = v
			filename = re.sub (k, '', filename)
			
	prefixes = [("b", "Bold"),
		    ("d", "Demi bold")]
	weight = 'Regular'
	for (k, v) in prefixes:
		if re.search (k, filename):
			weight = v
			filename = re.sub (k, '', filename)

	prefixes = [("c", "Condensed"),
		    ("x", "Extended")]
	stretch = ''
	for (k, v) in prefixes:
		if re.search (k, filename):
			stretch = v
			filename = re.sub (k, '', filename)
	
	fontinfo['ItalicAngle'] = 0
	if re.search ('[Ii]talic', shape) or re.search ('[Oo]blique', shape):
		a = -14
		if re.search ("Sans", family):
			a = -12

		fontinfo ["ItalicAngle"] = a

	fontinfo['Weight'] = weight
	fontinfo['FamilyName'] = family
	full  = '%s %s %s %s %dpt' \
			       % (family, shape, weight, stretch, design_size)
	full = re.sub (" +", ' ', full)
	
	fontinfo['FullName'] = full
	fontinfo['FontName'] = derive_font_name (family, full)

	return fontinfo

def ec_guess_font_info (filename, fontinfo):
	design_size = 12
	m = re.search ("([0-9]+)$", filename)
	if m:
		design_size = string.atoi (m.group (1))
		fontinfo['DesignSize'] = design_size

	prefixes = [("ecss", "European Computer Modern Sans"),
		    ("ectt", "European Computer Modern Typewriter"),
		    ("ec", "European Computer Modern")]

	family = ''
 	for (k, v) in prefixes:
		if re.search (k, filename):
			if k == 'ectt':
				fontinfo['isFixedPitch'] = 'true'
			family = v
			filename = re.sub (k, '', filename)
			break

	# shapes
	prefixes = [("r", "Roman"),
		    ("mi", "Math italic"),
		    ("u", "Unslanted italic"),
		    ("sl", "Oblique"),
		    ("cc", "Small caps"),
		    ("ex", "Math extension"),
		    ("ti", "Italic"),
		    ("i", "Italic")]
	
	shape = ''
 	for (k, v) in prefixes:
		if re.search (k, filename):
			shape = v
			filename = re.sub (k, '', filename)

	prefixes = [("b", "Bold"),
		    ("d", "Demi bold")]
	weight = 'Regular'
	for (k, v) in prefixes:
		if re.search (k, filename):
			weight = v
			filename = re.sub (k, '', filename)

	prefixes = [("c", "Condensed"),
		    ("x", "Extended")]
	stretch = ''
	for (k, v) in prefixes:
		if re.search (k, filename):
			stretch = v
			filename = re.sub (k, '', filename)
	
	fontinfo['ItalicAngle'] = 0
	if re.search ('[Ii]talic', shape) or re.search ('[Oo]blique', shape):
		a = -14
		if re.search ("Sans", family):
			a = -12

		fontinfo ["ItalicAngle"] = a

	fontinfo['Weight'] = weight
	fontinfo['FamilyName'] = family
	full  = '%s %s %s %s %dpt' \
			       % (family, shape, weight, stretch, design_size)
	full = re.sub (" +", ' ', full)
	
	fontinfo['FontName'] = derive_font_name (family, full)
	fontinfo['FullName'] = full

	return fontinfo

afmfile = ''
def guess_fontinfo (filename):
	fi = {
		'FontName': filename,
		'FamilyName': filename,
		'Weight': 'Regular',
		'ItalicAngle': 0,
		'DesignSize' : 12,
		'isFixedPitch' : 'false',
		'FullName': filename,
	       }

	if re.search ('^cm', filename):
		fi.update (cm_guess_font_info (filename, fi))
	elif re.search ("^ec", filename):
		fi.update (ec_guess_font_info (filename, fi))
	elif read_afm_p:
		global afmfile
		if not afmfile:
			afmfile = find_file (filename + '.afm')

		if afmfile:
			afmfile = os.path.abspath (afmfile)
			afm_struct = afm.read_afm_file (afmfile)
			fi.update (afm_struct.__dict__)
		return fi
	else:
		sys.stderr.write ("Warning: no extra font information for this font.\n"
				  + "Consider writing a XX_guess_font_info() routine.\n")

	return fi

tfmfile = ''
output_name = ''
gf_fontname = ''
encoding_file_override = ''
glyph_range = []
glyph_ranges = []
glyph_subrange = []
for (o, a) in options:
	if 0:
		pass
	elif o == '--help' or o == '-h':
		help ()
		sys.exit (0)
	elif o == '--keep' or o == '-k':
		keep_temp_dir_p = 1
	elif o == '--verbose' or o == '-V':
		verbose_p = 1
	elif o == '--keep-trying':
		keep_trying_p = 1
	elif o == '--version' or o == '-v':
		identify (sys.stdout)
		sys.exit (0)
	elif o == '--warranty' or o == '-w':
		warranty ()
		sys.exit (0)
	elif o == '--encoding' or o == '-e':
		encoding_file_override = a
	elif o == '--gffile':
		gf_fontname = a
	elif o == '--glyphs':
		glyph_ranges = string.split (a, ',')
		for r in glyph_ranges:
			glyph_subrange = map (string.atoi, string.split (r, '-'))
			if len (glyph_subrange) == 2 and glyph_subrange[0] < glyph_subrange[1] + 1:
				glyph_range.extend (range (glyph_subrange[0], glyph_subrange[1] + 1))
			else:
				glyph_range.append (glyph_subrange[0])
	elif o == '--tfmfile':
		tfmfile = a
	elif o == '--dos-kpath':
		dos_kpath_p = 1
	elif o == '--formats' or o == '-f':
		formats = string.split (string.lower (a), ',') 
	elif o == '--include' or o == '-I':
		include_dirs.append (a)
	elif o == '--simplify':
		simplify_p = 1
	elif o == '--magnification':
		magnification = string.atof (a)
	elif o == '--potrace':
		trace_binary = 'potrace'
	elif o == '--autotrace':
		trace_binary = 'autotrace'
	elif o == '--noround':
		round_to_int = 0
	elif o == '--no-afm':
		read_afm_p = 0
	elif o == '--grid':
		potrace_scale = round (string.atof (a))
	else:
		raise 'Ugh -- forgot to implement option: %s.)' % o


backend_options = getenv ('MFTRACE_BACKEND_OPTIONS', '')

stat = os.system ('potrace --version > /dev/null 2>&1 ')
if trace_binary != 'autotrace' and stat == 0:
	trace_binary = 'potrace'
	trace_command = potrace_command
	path_to_type1_ops = potrace_path_to_type1_ops

stat = os.system ('autotrace --version > /dev/null 2>&1 ')
if trace_binary != 'potrace' and stat == 0:
	trace_binary = 'autotrace'
	trace_command = autotrace_command
	path_to_type1_ops = autotrace_path_to_type1_ops

if not trace_binary:
	error (_ ("No tracing program found. Exit."))


identify (sys.stderr)
if formats == []:
	formats = ['pfa']
	
if not files:
	try:
		error ("No input files specified.")
	except:
		pass
	help ()
	sys.exit (2)

for filename in files:
	encoding_file = encoding_file_override

	basename = strip_extension (filename, '.mf')
	progress (_ ("Font `%s'..." % basename))
	progress ('\n')

	if not tfmfile:
		tfmfile = find_file (basename + '.tfm')

	if not tfmfile:
		tfmfile = popen ("mktextfm %s 2>/dev/null" % basename).read ()
		if tfmfile:
			tfmfile = tfmfile[:-1]

	if not tfmfile:
		error (_ ("Can not find a TFM file to match `%s'") % basename)

	tfmfile = os.path.abspath (tfmfile)
	metric = tfm.read_tfm_file (tfmfile)

	fontinfo = guess_fontinfo (basename)


	if encoding_file and not os.path.exists (encoding_file):
		encoding_file = find_file (encoding_file)


	if not encoding_file:
		codingfile = 'tex256.enc'
		if not coding_dict.has_key (metric.coding):
			sys.stderr.write ("Unknown encoding `%s'; assuming tex256.\n" % metric.coding)
		else:
			codingfile = coding_dict[metric.coding]

		encoding_file = find_file (codingfile)
		if not encoding_file:
			error (_ ("can't find file `%s'" % codingfile))

	(enc_name, encoding) = read_encoding (encoding_file)

	if not len (glyph_range):
		glyph_range = range (0, len (encoding))

	temp_dir = setup_temp ()

	if verbose_p:
		progress ('Temporary directory is `%s\' ' % temp_dir)

	include_dirs.append (os.getcwd ())
	os.chdir (temp_dir)

	if not gf_fontname:
		# run mf
		base = gen_pixel_font (basename, metric, magnification)
		gf_fontname = base + 'gf'
	else:
		gf_fontname = find_file (gf_fontname)

	# the heart of the program:
	trace_font (basename, gf_fontname, metric, glyph_range, encoding,
		    magnification, fontinfo)
		
	make_outputs (basename, formats)
	for format in formats:
		shutil.copy2 (basename + '.' + format, origdir)

	os.chdir (origdir)
	cleanup_temp ()

sys.exit (exit_value)
