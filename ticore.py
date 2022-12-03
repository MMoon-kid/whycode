# !/bin/env python3
# -*- coding: utf-8 -*-
# library for some shader functions.

import os
import time
import math
import taichi as ti
from pydub import AudioSegment
from pydub.playback import play


ti.init(arch=ti.gpu, default_ip=ti.i32, default_fp=ti.f32)

# ================================================common================================================
# res = (960, 540)
# res = (1920, 1080)
# res = (2560, 1600)
res = (2560//2, 1600//2)
t = 0.0
fps = 60.0
dt = 1.0 / fps
pixels = ti.Vector.field(n=4, dtype=float, shape=res)  # write color [rgba]
pixels_dis = ti.Vector.field(n=3, dtype=float, shape=res)  # display [rgb]
clear_color = ti.Vector([0.12, 0.12, 0.12, 1.0])

# ================================================star================================================
fov = 120
tan_half_fov = math.tan(fov / 360 * math.pi)
z_near, z_far, grid_size = 200, 3200, 80
N = (res[0]//grid_size, res[1]//grid_size, (z_far - z_near) // grid_size)
pos = ti.Vector.field(n=3, dtype=float, shape=N)
color = ti.Vector.field(n=3, dtype=float, shape=N)
vel = ti.Vector.field(n=3, dtype=float, shape=())


# ================================================music================================================
def PlayMusic(threadName,  music):
    print("Start play " + threadName)
    play(music)
    print("End play " + threadName)


# ================================================tools================================================
@ti.func
def rand3():
    return ti.Vector([ti.random(), ti.random(), ti.random()])


@ti.func
def rand4():
    return ti.Vector([ti.random(), ti.random(), ti.random(), 1.0])


@ti.func
def clamp(x, low=0.0, high=1.0):
    ret = x
    if x > high:
        ret = high
    elif x < low:
        ret = low
    return ret


@ti.func
def sign(x):
    if x >= 0:
        x = 1.0
    elif x < 0.0:
        x = -1.0
    return x


@ti.func
def fract(x):
    return x - ti.floor(x)


@ti.func
def smoothstep(edge0, edge1, x):
    t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


@ti.func
def mix(x, y, a):
    # x * (1.0 - a) + y * a
    return x * (1.0 - a) + y * a


@ti.func
def tooth(x):
    # /\/\/\/\/\
    return ti.min(fract(x * 2.0), 1.0 - fract(x * 2.0)) * 2.0


@ti.func
def dot2(x):
    return x.dot(x)


@ti.func
def Union(d1, d2):
    return min(d1, d2)


@ti.func
def Subtraction(d1, d2):
    # return max(-d1, d2) # maybe has erro.
    return max(d1, -d2)


@ti.func
def Intersection(d1, d2):
    return max(d1, d2)


@ti.func
def SmoothUnion(d1, d2, k):
    h = clamp(0.5 + 0.5 * (d2 - d1) / k, 0.0, 1.0)
    return mix(d2, d1, h) - k * h * (1.0 - h)


@ti.func
def SmoothSubstraction(d1, d2, k):
    h = clamp(0.5 - 0.5 * (d2 + d1) / k, 0.0, 1.0)
    return mix(d2, -d1, h) - k * h * (1.0 - h)


@ti.func
def SmoothIntersection(d1, d2, k):
    h = clamp(0.5 - 0.5 * (d2 - d1) / k, 0.0, 1.0)
    return mix(d2, d1, h) - k * h * (1.0 - h)


@ti.func
def convert_0to1_smooth(x, maxv=1.0):
    return ti.sin(x / maxv * math.pi * 0.5)  # return [0, 1] with sin smooth


@ti.func
def convert_whole_smooth(x, maxv=1.0):
    return ti.sin(x / maxv * math.pi * 2.0)  # return [0, 1, 0, -1, 0] with sin smooth


@ti.func
def combine(x, y):
    # combine RGBA color. y : high level, x : low level
    col = ti.Vector([0.0, 0.0, 0.0, 0.0])
    r = y[0] * y[3] + x[0] * x[3] * (1.0 - y[3])
    g = y[1] * y[3] + x[1] * x[3] * (1.0 - y[3])
    b = y[2] * y[3] + x[2] * x[3] * (1.0 - y[3])
    a = 1.0 - (1.0 - y[3]) * (1.0 - x[3])
    r = r / a
    g = g / a
    b = b / a
    r = clamp(r)
    g = clamp(g)
    b = clamp(b)
    a = clamp(a)
    col = ti.Vector([r, g, b, a])
    return col

# ================================================sdf================================================


@ti.func
def sdf_star(uv, rf, rad):
    # generate distance field of 2D-stars
    k1 = ti.Vector([0.809016994375, -0.587785252292])
    k2 = ti.Vector([-k1[0], k1[1]])
    uv[0] = ti.abs(uv[0])
    uv -= 2.0 * ti.max(k1.dot(uv), 0.0) * k1
    uv -= 2.0 * ti.max(k2.dot(uv), 0.0) * k2
    uv[0] = ti.abs(uv[0])
    uv[1] -= rad

    ba = rf * ti.Vector([-k1[1], k1[0]]) - ti.Vector([0.0, 1.0])
    h = uv.dot(ba) / ba.dot(ba)
    h = clamp(h, 0.0, rad)  # use clmap for good render.

    v = uv[1] * ba[0] - uv[0] * ba[1]
    v = sign(v)

    dist = (uv - ba * h).norm() * v  # diatance field of 2D-stars
    return dist


@ti.func
def sdf_sphere(uv, rad):
    return uv.norm() - rad


@ti.func
def sdf_box(pos, size):
    d = ti.abs(pos) - size
    dist = ti.max(d, 0.0).norm()
    dist = dist + ti.min(ti.max(d.x, d.y), 0.0)
    return dist


@ti.func
def sdf_arc(pos, sc, ra, rb):
    # pos.x = ti.abs(pos.x)
    dist = 0.0
    if sc.y * pos.x > sc.x * pos.y:
        dist = (pos - sc * ra).norm()
    else:
        dist = ti.abs(pos.norm() - ra) - rb
    return dist


@ti.func
def sdf_line(pos, ang):
    n = ti.floor(ang / (2.0 * math.pi))
    ang = ang - 2.0 * math.pi * n
    k = ti.tan(ang)
    dist = (k * pos[0] - pos[1]) / ti.sqrt(k * k + 1)
    if ang > 0.5 * math.pi and ang < 1.5 * math.pi:
        dist = - dist
    return dist


@ti.func
def sdf_taichi(pos, radius, ang, padding=0.01, inner_radius=0.2, step=0):
    sub_offset = ti.Vector([ti.cos(ang), ti.sin(ang)]) * radius * 0.5
    d = sdf_sphere(pos, radius)
    d1 = sdf_sphere(pos - sub_offset, radius * 0.5)
    d0 = sdf_sphere(pos + sub_offset, radius * 0.5)
    dl = sdf_line(pos, ang)

    dist0 = ti.max(ti.min(ti.max(d, dl - padding), d0), -d1) + padding
    dist1 = ti.max(ti.min(ti.max(d, -dl - padding), d1), -d0) + padding
    dist = 0.0
    if step > -1:
        dist = dist0
    if step > 0:
        dist = dist1
    if step > 1:
        dist = ti.min(dist0, dist1)
    if step > 2:
        dist = ti.max(dist, -(d0 + inner_radius))
        dist = ti.max(dist, -(d1 + inner_radius))
    return dist


@ti.func
def sdf_tri(p, p0, p1, p2):
    dist = 0.0
    e0 = p1 - p0
    e1 = p2 - p1
    e2 = p0 - p2
    v0 = p - p0
    v1 = p - p1
    v2 = p - p2
    pq0 = v0 - e0 * clamp(v0.dot(e0) / e0.dot(e0), 0.0, 1.0)
    pq1 = v1 - e1 * clamp(v1.dot(e1) / e1.dot(e1), 0.0, 1.0)
    pq2 = v2 - e2 * clamp(v2.dot(e2) / e2.dot(e2), 0.0, 1.0)

    s = sign(e0.x * e2.y - e0.y * e2.x)
    d = ti.Vector([pq0.dot(pq0), s * (v0.x * e0.y - v0.y * e0.x)])
    d = ti.min(d, ti.Vector([pq1.dot(pq1), s * (v1.x * e1.y - v1.y * e1.x)]))
    d = ti.min(d, ti.Vector([pq2.dot(pq2), s * (v2.x * e2.y - v2.y * e2.x)]))

    dist = -ti.sqrt(d.x) * sign(d.y)
    return dist


@ti.func
def sdf_tree(uv, height=2, width=0.05):
    p0 = ti.Vector([0.0, 0.45])
    p1 = ti.Vector([0.18, 0.18])
    p2 = ti.Vector([-0.18, 0.18])
    dist = sdf_tri(uv, p0, p1, p2)
    for i in range(height):
        offset = 0.43 / height
        p0 = p0 - ti.Vector([0.0, offset * 0.5])
        p1 = p1 - ti.Vector([-offset * 0.18, offset + i * 0.02])
        p2 = p2 - ti.Vector([offset * 0.18, offset + i * 0.02])
        trii = sdf_tri(uv, p0, p1, p2)
        dist = ti.min(dist, trii)
    c = ti.Vector([0.0, -0.25])
    bb = ti.Vector([0.05, 0.3])
    truck = sdf_box(uv - c, bb)
    dist = ti.min(dist, truck)
    return dist


@ti.func
def sdf_egg(p, ra, rb):
    dist = 0.0
    k = ti.sqrt(3.0)
    p.x = ti.abs(p.x)
    r = ra - rb

    f = 0.0
    f2 = 0.0
    d1 = ti.Vector([p.x, p.y - k * r]).norm()
    d2 = ti.Vector([p.x + r, p.y]).norm() - 2.0 * r
    if k * (p.x + r) < p.y:
        f2 = d1
    else:
        f2 = d2
    f1 = p.norm() - r

    if p.y < 0.0:
        f = f1
    else:
        f = f2

    dist = f - rb
    return dist


@ti.func
def sdf_heart(p):
    dist = 0.0
    p.x = ti.abs(p.x)
    if ((p.x + p.y) > 1.0):
        dist = ti.sqrt(dot2(p - ti.Vector([0.25, 0.75]))) - ti.sqrt(2.0) / 4.0
    else:
        dist = ti.min(dot2(p - ti.Vector([0.0, 1.0])), dot2(p - 0.5 * ti.max(p.x + p.y, 0.0)))
        dist = ti.sqrt(dist) * sign(p.x - p.y)
    return dist


@ti.func
def sdf_multi_circle(uv, radius=0.5, thickness=0.006):
    dist = ti.abs(sdf_sphere(uv, radius)) - thickness
    return dist


@ti.func
def sdf_flower(uv):
    pass

# ================================================render================================================


@ti.func
def blink_col():
    pass


inner_col = ti.Vector([0.25, 0.85, 1.0])
outer_col = ti.Vector([0.65, 0.35, 0.76])


@ti.func
def render_grad(dist, cnt=350):
    # ref: https://github.com/ElonKou/biulab/blob/master/shaders/shadertoy/sdf2d1.fs
    col = ti.Vector([0.0, 0.0, 0.0])
    if (dist < 0.0):
        col = inner_col
    else:
        col = outer_col
    col = col * (1.0 - ti.exp(-6.0 * ti.abs(dist)))
    col = col * (0.8 + 0.2 * ti.cos(dist * cnt))
    c = smoothstep(0.0, 0.01, ti.abs(dist))
    col = mix(col, ti.Vector([1.0, 1.0, 1.0]), 1.0 - c)

    ret = ti.Vector([col[0], col[1], col[2], 1.0])
    return ret


@ti.func
def render_general(dist):
    col = ti.Vector([0.0, 0.0, 0.0, 0.0])
    if dist < 0.0:
        col = ti.Vector([0.34, 0.45, 0.56, 1.0])
    return col


@ti.func
def render_black(dist, uv):
    col = ti.Vector([0.4, 0.2, 0.12, 1.0])
    col_purple = ti.Vector([0.99, 0.25, 0.94, 1.0])
    col_blue = ti.Vector([0.24, 0.75, 0.89, 1.0])
    d = uv.norm()
    if dist < 0.0:
        col = mix(col_purple, col_blue, 1.0 - d)
    else:
        col = mix(col_purple, col_blue, 1.0 - d)
        col[3] = col[3] * max(0.03 - dist, 0.0)

    return col


@ti.func
def render_total_black(dist):
    white = ti.Vector([0.9, 0.9, 0.9, 1.0])
    black = ti.Vector([0.02, 0.02, 0.02, 1.0])
    dist = white
    if dist < 0.0:
        dist = black
    return dist


@ti.func
def render_blink(dist, t):
    col = ti.Vector([0.0, 0.0, 0.0, 0.0])
    if dist < 0.0:
        col = ti.Vector([0.7 + ti.sin(t * 8.03) * 0.3, 0.9 * ti.sin(dist * 2 + 1.0), 0.7, 1.0])
    return col


@ti.func
def render_scale(dist, t):
    dist = dist * ti.sin(t) * 1.45
    col = render_grad(dist, 250)
    col.x = mix(col.x, 1.0, ti.sin(t * 2.3) * 0.9)
    col.z = mix(col.z, 1.0, ti.cos(t * 3.1) * 0.9)
    col.y = mix(col.y, 0.0, ti.sin(t * 0.67) * 0.3)
    return col


@ti.func
def fade_in(t, offset=1.0):
    return ti.min(ti.exp(t + offset), t)


@ti.func
def perid_time(x, up=1.0, dura=2.0):
    # |  ____
    # |/______\__

    scale = dura + up * 2.0
    ret = fract(x / scale) * scale
    ret = ti.min(ret, scale - ret)
    ret = ti.min(ret, up)
    return ret


@ti.func
def render_in(dist, t):
    c = fade_in(t)
    dist = dist * ti.sin(c) * 1.45
    col = render_grad(dist, min(c * 13, 250))
    col.x = mix(col.x, 1.0, ti.sin(c * 2.3) * 0.9)
    col.z = mix(col.z, 1.0, ti.cos(c * 3.1) * 0.9)
    col.y = mix(col.y, 0.0, ti.sin(c * 0.67) * 0.3)
    return col
