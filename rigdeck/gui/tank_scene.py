"""The tank: a porthole into glowing coolant, with one number surfacing from it and the
site's logo turning above. Runs inside Blender, never inside the app:

  blender -b --python tank_scene.py -- color=#ff2f3f value=2603 prefix=+ decimals=0 logo=PNG out=DIR res=384 samples=72 frames=0-174 font=TTF

Every motion completes whole cycles over `total` frames (default 175, 7 s at 25 fps), so a
segment loops without a seam and segments join without a jump. The finishing step in tank.py
adds the labels afterwards, so a changed label never needs a new render.
"""
import math, random, sys
import bpy, bmesh

args = dict(a.split('=', 1) for a in sys.argv[sys.argv.index('--') + 1:]) if '--' in sys.argv else {}
COLOR = args.get('color', '#ff2f3f'); TEXT = args.get('text', ''); OUT = args.get('out', '/tmp/tank')
RES = int(args.get('res', 320)); SAMPLES = int(args.get('samples', 128)); TOTAL = int(args.get('total', 175))
first, last = (int(v) for v in args.get('frames', '0-0').split('-'))
FONT = args.get('font', ''); LEVEL = float(args.get('level', -0.30))
VALUE = float(args.get('value', '0') or 0); LOGO = args.get('logo', ''); PREFIX = args.get('prefix', ''); DECIMALS = int(args.get('decimals', 0))
def shown(v): return f'{PREFIX}{v:,.{DECIMALS}f}'
from mathutils import Vector

def rgb(h, gamma=True):
    h = h.lstrip('#'); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple((v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c) if gamma else tuple(c)
C = rgb(COLOR)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
world = bpy.data.worlds.new('w'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0, 0, 0, 1)

def material(name, **inputs):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    for k, v in inputs.items():
        b.inputs[k].default_value = v
    return m

def add(obj_data, name, mat=None, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, obj_data); scene.collection.objects.link(o); o.location = loc
    if mat: o.data.materials.append(mat)
    return o

def box(name, lo, hi, mat):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = tuple(lo[i] + (v.co[i] + .5) * (hi[i] - lo[i]) for i in range(3))
    bm.to_mesh(me); bm.free(); return add(me, name, mat)

# ---- tank: a dark ribbed chamber behind the window ------------------------------------------
steel = material('steel', **{'Base Color': (.16, .17, .19, 1), 'Metallic': 1.0, 'Roughness': .34})
wall = material('wall', **{'Base Color': (.012, .014, .018, 1), 'Metallic': .9, 'Roughness': .55})
X, Y0, Y1, Z = 1.9, 0.07, 2.3, 1.9
for lo, hi in [((-X, Y1, -Z), (X, Y1 + .1, Z)), ((-X - .1, Y0, -Z), (-X, Y1, Z)), ((X, Y0, -Z), (X + .1, Y1, Z)),
               ((-X, Y0, -Z - .1), (X, Y1, -Z)), ((-X, Y0, Z), (X, Y1, Z + .1))]:
    box('tank', lo, hi, wall)
for i in range(0):                       # ribs on the back wall catch the coloured light and give depth
    z = -1.5 + i * .5
    box('rib', (-X, Y1 - .05, z - .028), (X, Y1, z + .028), steel)

# ---- bezel: a machined lip with bolts ------------------------------------------------------
me = bpy.data.meshes.new('bezel'); bm = bmesh.new()
profile = [(.948, .06), (.948, -.015), (.958, -.045), (.99, -.06), (1.2, -.06), (1.2, .06)]   # (radius, y)
SEG = 128; rings = []
for r, y in profile:
    rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / SEG), y, r * math.sin(2 * math.pi * i / SEG))) for i in range(SEG)])
for a, b in zip(rings, rings[1:] + rings[:1]):
    for i in range(SEG):
        bm.faces.new((a[i], a[(i + 1) % SEG], b[(i + 1) % SEG], b[i]))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
for p in me.polygons: p.use_smooth = True
bezel = add(me, 'bezel', steel)
bolt = material('bolt', **{'Base Color': (.05, .055, .065, 1), 'Metallic': 1.0, 'Roughness': .28})
for i in range(0):
    a = 2 * math.pi * (i + .5) / 12
    bme = bpy.data.meshes.new('bolt'); bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=.026, radius2=.022, depth=.03)
    bm.to_mesh(bme); bm.free()
    o = add(bme, 'bolt', bolt, (.951 * math.cos(a), -.105, .951 * math.sin(a))); o.rotation_euler = (math.pi / 2, 0, a)

# ---- glass: a shallow dome, so it carries one soft highlight -----------------------------
gme = bpy.data.meshes.new('glass'); bm = bmesh.new()
R, cap = 3.2, .952
def dome(offset):
    rows = []
    for j in range(25):
        r = cap * j / 24; y = -(math.sqrt(R * R - r * r) - math.sqrt(R * R - cap * cap)) + offset
        rows.append([bm.verts.new((r * math.cos(2 * math.pi * i / 96), y, r * math.sin(2 * math.pi * i / 96))) for i in range(96)] if j else [bm.verts.new((0, y, 0))])
    for a, b in zip(rows[1:], rows[2:]):
        for i in range(96): bm.faces.new((a[i], a[(i + 1) % 96], b[(i + 1) % 96], b[i]))
    for i in range(96): bm.faces.new((rows[0][0], rows[1][i], rows[1][(i + 1) % 96]))
    return rows[-1]
outer, inner = dome(0.0), dome(0.035)
for i in range(96): bm.faces.new((outer[i], outer[(i + 1) % 96], inner[(i + 1) % 96], inner[i]))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(gme); bm.free()
for p in gme.polygons: p.use_smooth = True
add(gme, 'glass', material('glass', **{'Base Color': (1, 1, 1, 1), 'Transmission Weight': 1.0, 'Roughness': .0, 'IOR': 1.48}), (0, .02, 0))

# ---- liquid --------------------------------------------------------------------------------
liquid = bpy.data.materials.new('liquid'); liquid.use_nodes = True
nt = liquid.node_tree; b = nt.nodes['Principled BSDF']
b.inputs['Base Color'].default_value = (1, 1, 1, 1); b.inputs['Transmission Weight'].default_value = 1.0
b.inputs['Roughness'].default_value = 0.0; b.inputs['IOR'].default_value = 1.33
absorb = nt.nodes.new('ShaderNodeVolumeAbsorption'); scatter = nt.nodes.new('ShaderNodeVolumeScatter'); glow = nt.nodes.new('ShaderNodeEmission')
sat = tuple(max(.02, c) ** 1.25 for c in C)
absorb.inputs['Color'].default_value = (*sat, 1); absorb.inputs['Density'].default_value = float(args.get('density', 1.6))
scatter.inputs['Color'].default_value = (*tuple(.15 + .85 * c for c in C), 1); scatter.inputs['Density'].default_value = float(args.get('scatter', .13))
scatter.inputs['Anisotropy'].default_value = .6
glow.inputs['Color'].default_value = (*C, 1); glow.inputs['Strength'].default_value = float(args.get('glow', .05))
a1 = nt.nodes.new('ShaderNodeAddShader'); a2 = nt.nodes.new('ShaderNodeAddShader')
nt.links.new(absorb.outputs[0], a1.inputs[0]); nt.links.new(scatter.outputs[0], a1.inputs[1])
nt.links.new(a1.outputs[0], a2.inputs[0]); nt.links.new(glow.outputs[0], a2.inputs[1])
nt.links.new(a2.outputs[0], nt.nodes['Material Output'].inputs['Volume'])

NX, NY = 150, 70
WAVES = [(.040, 2.3, .9, 2, .0), (.026, -3.6, 2.1, 3, 1.7), (.016, 6.5, -1.3, 5, 4.1), (.010, -9.0, 4.0, 7, 2.6), (.022, 1.1, 3.3, 1, 5.2)]
NUM_Y = float(args.get('numy', .62)); EMERGE = .12
def level_at(t):
    return LEVEL + .018 * math.sin(2 * math.pi * t)
def height(x, y, t):                    # t in [0,1): every term completes whole cycles, so it loops
    h = level_at(t) + sum(a * math.sin(kx * x + ky * y - 2 * math.pi * n * t + p) for a, kx, ky, n, p in WAVES)
    tau = (t - EMERGE) * TOTAL / 25      # seconds since the number broke the surface
    if tau > 0:
        r = math.hypot(x, y - NUM_Y)
        h += .04 * math.exp(-tau / 1.0) * (1 - math.exp(-tau * 6)) * math.cos(9 * r - 7.5 * tau) * math.exp(-r / .9)
    return h

lme = bpy.data.meshes.new('liquid'); bm = bmesh.new()
top = [[bm.verts.new((-X + 2 * X * i / NX, Y0 + (Y1 - Y0) * j / NY, LEVEL)) for i in range(NX + 1)] for j in range(NY + 1)]
bot = [[bm.verts.new((-X + 2 * X * i / NX, Y0 + (Y1 - Y0) * j / NY, -Z)) for i in (0, NX)] for j in (0, NY)]
for j in range(NY):
    for i in range(NX): bm.faces.new((top[j][i], top[j][i + 1], top[j + 1][i + 1], top[j + 1][i]))
bm.faces.new((bot[0][0], bot[1][0], bot[1][1], bot[0][1]))
for i in range(NX): bm.faces.new((top[0][i], bot[0][0] if i == 0 else top[0][i], top[0][i + 1])) if False else None
# sides: fan each edge of the top down to the two bottom corners of that side
def side(edge, a, b):
    bm.faces.new([a] + edge + [b])
side([top[0][i] for i in range(NX + 1)], bot[0][0], bot[0][1])
side([top[NY][i] for i in range(NX + 1)], bot[1][0], bot[1][1])
side([top[j][0] for j in range(NY + 1)], bot[0][0], bot[1][0])
side([top[j][NX] for j in range(NY + 1)], bot[0][1], bot[1][1])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(lme); bm.free()
for p in lme.polygons: p.use_smooth = True
liq = add(lme, 'liquid', liquid)
TOP = [(v.index, v.co.x, v.co.y) for v in lme.vertices if abs(v.co.z - LEVEL) < 1e-6]

# ---- bubbles: air rising through the liquid ---------------------------------------------
air = material('air', **{'Base Color': (1, 1, 1, 1), 'Transmission Weight': 1.0, 'Roughness': 0.0, 'IOR': 0.76})
random.seed(7); BUBBLES = []
sph = bpy.data.meshes.new('bubble'); bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=1)
bm.to_mesh(sph); bm.free()
for p in sph.polygons: p.use_smooth = True
for _ in range(int(args.get('bubbles', 46))):
    o = add(sph, 'bubble', air); r = random.uniform(.010, .034); o.scale = (r, r, r)
    BUBBLES.append((o, random.uniform(-.9, .9), random.uniform(.16, 1.2), random.random(), random.choice((1, 1, 2)), random.uniform(0, 6.28), r))

# ---- the number, standing in the tank ------------------------------------------------------
FINAL = shown(VALUE) if 'value' in args else TEXT
cu = bpy.data.curves.new('num', 'FONT'); cu.body = FINAL
if FONT: cu.font = bpy.data.fonts.load(FONT)
cu.align_x = 'CENTER'; cu.align_y = 'CENTER'; cu.extrude = .07; cu.bevel_depth = .012; cu.bevel_resolution = 2
glowm = material('num', **{'Base Color': (1, 1, 1, 1), 'Emission Color': (.93, .98, 1, 1), 'Emission Strength': float(args.get('numglow', 1.25)), 'Roughness': .22})
NUM_Z = float(args.get('numz', -.125))
num = add(cu, 'num', glowm, (0, NUM_Y, NUM_Z)); num.rotation_euler = (math.pi / 2, 0, 0)
bpy.context.view_layer.update()
width = num.dimensions.x or 1; s = min(float(args.get('numw', 1.42)) / width, 1.0); num.scale = (s, s, s)

# ---- the logo: a lit sign hanging in the tank, so it turns in, sways and mirrors in the liquid
logo = None
if LOGO:
    img = bpy.data.images.load(LOGO); aspect = img.size[0] / max(1, img.size[1])
    w = min(.9, .46 * aspect); h = w / aspect
    logo = bpy.data.objects.new('logo', None); scene.collection.objects.link(logo); logo.location = (0, .5, float(args.get('logoz', .53)))
    def face_material(name, gain, glow):
        m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; b = nt.nodes['Principled BSDF']
        tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img; tex.extension = 'CLIP'
        # read the right way round from behind too: mirror the picture on back faces
        geo = nt.nodes.new('ShaderNodeNewGeometry'); uvn = nt.nodes.new('ShaderNodeUVMap'); sep = nt.nodes.new('ShaderNodeSeparateXYZ')
        flip = nt.nodes.new('ShaderNodeMath'); flip.operation = 'SUBTRACT'; flip.inputs[0].default_value = 1.0
        pick = nt.nodes.new('ShaderNodeMix'); pick.data_type = 'FLOAT'; comb = nt.nodes.new('ShaderNodeCombineXYZ')
        nt.links.new(uvn.outputs['UV'], sep.inputs[0]); nt.links.new(sep.outputs['X'], flip.inputs[1])
        nt.links.new(geo.outputs['Backfacing'], pick.inputs[0]); nt.links.new(sep.outputs['X'], pick.inputs[2]); nt.links.new(flip.outputs[0], pick.inputs[3])
        nt.links.new(pick.outputs[0], comb.inputs['X']); nt.links.new(sep.outputs['Y'], comb.inputs['Y']); nt.links.new(comb.outputs[0], tex.inputs['Vector'])
        dim = nt.nodes.new('ShaderNodeMixRGB'); dim.blend_type = 'MULTIPLY'; dim.inputs['Fac'].default_value = 1.0
        dim.inputs['Color2'].default_value = (gain, gain, gain, 1); nt.links.new(tex.outputs['Color'], dim.inputs['Color1'])
        nt.links.new(dim.outputs[0], b.inputs['Base Color']); nt.links.new(dim.outputs[0], b.inputs['Emission Color'])
        nt.links.new(tex.outputs['Alpha'], b.inputs['Alpha'])
        b.inputs['Emission Strength'].default_value = glow; b.inputs['Metallic'].default_value = .55; b.inputs['Roughness'].default_value = .26
        return m
    faces = face_material('logo-face', 1.0, float(args.get('logoglow', 1.15)))
    sides = face_material('logo-side', .30, .45)
    LAYERS, DEPTH = 15, float(args.get('logodepth', .085))        # a stack of cut-outs reads as one solid, extruded mark
    for i in range(LAYERS):
        y = -DEPTH / 2 + DEPTH * i / (LAYERS - 1)
        pm = bpy.data.meshes.new('logo'); bm = bmesh.new()
        vs = [bm.verts.new(c) for c in ((-w / 2, y, -h / 2), (w / 2, y, -h / 2), (w / 2, y, h / 2), (-w / 2, y, h / 2))]
        face = bm.faces.new(vs); uv = bm.loops.layers.uv.new()
        for loop, c in zip(face.loops, ((0, 0), (1, 0), (1, 1), (0, 1))): loop[uv].uv = c
        if i == LAYERS - 1: bmesh.ops.reverse_faces(bm, faces=bm.faces)   # the back cover faces backwards
        bm.to_mesh(pm); bm.free()
        o = add(pm, 'logo-layer', faces if i in (0, LAYERS - 1) else sides); o.parent = logo

def clamp(u): return max(0.0, min(1.0, u))
def out_back(u):
    u = clamp(u); return 1 + 2.70158 * (u - 1) ** 3 + 1.70158 * (u - 1) ** 2
def out_cubic(u): return 1 - (1 - clamp(u)) ** 3

# ---- light ---------------------------------------------------------------------------------
def emitter(name, lo, hi, color, strength):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    e = nt.nodes.new('ShaderNodeEmission'); o = nt.nodes.new('ShaderNodeOutputMaterial')
    e.inputs['Color'].default_value = (*color, 1); e.inputs['Strength'].default_value = strength
    nt.links.new(e.outputs[0], o.inputs['Surface']); return box(name, lo, hi, m)
emitter('floor', (-X, Y0 + .2, -Z + .001), (X, Y1 - .1, -Z + .02), C, float(args.get('floor', 6)))        # underglow in the site's colour
emitter('sky', (-1.2, .5, Z - .03), (1.2, 1.9, Z - .01), (1, 1, 1), float(args.get('sky', 9)))             # cool light on the surface
def area(name, loc, rot, size, energy, color=(1, 1, 1), glossy=True):
    l = bpy.data.lights.new(name, 'AREA'); l.shape = 'DISK'; l.size = size; l.energy = energy; l.color = color
    o = bpy.data.objects.new(name, l); scene.collection.objects.link(o); o.location = loc; o.rotation_euler = rot
    o.visible_glossy = glossy; o.visible_transmission = glossy; return o
KEY = area('key', (-2.6, -3.2, 3.0), (math.radians(52), 0, math.radians(-38)), 3.0, float(args.get('key', 420)), glossy=False)  # rakes the bezel
RIM = area('rim', (2.8, -1.6, -2.4), (math.radians(118), 0, math.radians(58)), 2.4, float(args.get('rimlight', 160)), tuple(.45 + .55 * c for c in C), glossy=False)
area('glint', (-3.4, -5.0, 4.2), (math.radians(50), 0, math.radians(-34)), 4.5, float(args.get('glint', 0)))                 # one soft highlight on the dome
wn = world.node_tree; bg = wn.nodes['Background']; lp = wn.nodes.new('ShaderNodeLightPath'); grad = wn.nodes.new('ShaderNodeTexGradient')
ramp = wn.nodes.new('ShaderNodeValToRGB'); tc = wn.nodes.new('ShaderNodeTexCoord'); mix = wn.nodes.new('ShaderNodeMixRGB')
ramp.color_ramp.elements[0].color = (.0, .0, .0, 1); ramp.color_ramp.elements[1].color = (.55, .62, .7, 1)
wn.links.new(tc.outputs['Generated'], grad.inputs['Vector']); wn.links.new(grad.outputs['Fac'], ramp.inputs['Fac'])
mix.inputs[1].default_value = (0, 0, 0, 1); wn.links.new(lp.outputs['Is Glossy Ray'], mix.inputs['Fac']); wn.links.new(ramp.outputs['Color'], mix.inputs[2])
wn.links.new(mix.outputs['Color'], bg.inputs['Color']); bg.inputs['Strength'].default_value = float(args.get('env', .9))

cam = bpy.data.cameras.new('cam'); cam.lens = 108; cam.sensor_width = 36; cam.sensor_fit = 'HORIZONTAL'
co = bpy.data.objects.new('cam', cam); scene.collection.objects.link(co); co.location = (0, -6, 0); co.rotation_euler = (math.pi / 2, 0, 0)
scene.camera = co

# ---- render --------------------------------------------------------------------------------
scene.render.engine = 'CYCLES'; cy = scene.cycles
prefs = bpy.context.preferences.addons['cycles'].preferences
try:
    prefs.compute_device_type = 'OPTIX'; prefs.get_devices()
    for d in prefs.devices: d.use = d.type == 'OPTIX'
    cy.device = 'GPU'
except Exception as e:
    print('GPU unavailable, using CPU:', e)
cy.samples = SAMPLES; cy.use_denoising = True; cy.use_adaptive_sampling = True; cy.adaptive_threshold = .02
cy.transparent_max_bounces = 48; cy.max_bounces = 14; cy.transmission_bounces = 12; cy.volume_bounces = 2; cy.glossy_bounces = 6; cy.sample_clamp_indirect = 6
scene.render.resolution_x = scene.render.resolution_y = RES; scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
try:
    scene.view_settings.view_transform = args.get('view', 'Standard'); scene.view_settings.look = args.get('look', 'None')
except Exception as e:
    print('view settings:', e)
scene.view_settings.exposure = float(args.get('exposure', 0))

for f in range(first, last + 1):
    t = (f % TOTAL) / TOTAL
    for index, x, y in TOP:
        lme.vertices[index].co.z = height(x, y, t)
    lme.update()
    top_level = level_at(t)
    for o, x, y, phase, laps, wob, r in BUBBLES:
        u = (phase + laps * t) % 1.0
        z = -1.0 + u * (top_level - .03 + 1.0)
        o.location = (x + .02 * math.sin(wob + 2 * math.pi * 3 * t), y, z)
        grow = min(1.0, u * 8) * min(1.0, (1 - u) * 14)      # born small, gone at the surface
        o.scale = (r * grow,) * 3
    # the number surfaces counting up, drifts, and dives before the loop ends
    sunk = .64
    if t < .9: dz = -sunk * (1 - out_back((t - .05) / .17))
    else: dz = -sunk * ((t - .9) / .1) ** 2
    num.location = (.025 * math.sin(2 * math.pi * t), NUM_Y, NUM_Z + dz)
    if 'value' in args: cu.body = shown(VALUE * out_cubic((t - .05) / .27))
    # the logo never stops turning: it whips round as each new number surfaces, then turns slowly,
    # lingering face-on. Whole turns per loop, so segments join without a jump.
    if logo:
        yaw = 360 * (t - .62 * math.sin(4 * math.pi * t) / (4 * math.pi)) + 720 * out_cubic(t / .16)
        logo.rotation_euler = (0, 0, math.radians(yaw)); logo.location.x = .03 * math.sin(2 * math.pi * t)
    # the lights circle the window once per loop, so no highlight sits still on the frame
    for lamp, base in ((KEY, (-2.6, -3.2, 3.0)), (RIM, (2.8, -1.6, -2.4))):
        a = 2 * math.pi * t; x, y, z = base
        lamp.location = (x * math.cos(a) - z * math.sin(a), y, x * math.sin(a) + z * math.cos(a))
        lamp.rotation_euler = (-Vector(lamp.location)).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = f'{OUT}/f{f:04d}.png'
    bpy.ops.render.render(write_still=True)
print('done')
