# Third-party notices

Crazy Type reuses the following upstream projects as libraries (no engine
code is copied into this repository). Their licences apply to their code;
Crazy Type's own code is MIT (see LICENSE).

## terminaltexteffects — MIT License

Copyright (c) ChrisBuilds — https://github.com/ChrisBuilds/terminaltexteffects

Used as the animation engine: every effect in `crazytype effects` is rendered
by the installed `terminaltexteffects` package via its public effect API
(`effect_class(input_data)` + `effect.terminal_output()`).

MIT licence text (from the upstream project):

> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

## pyfiglet — BSD-2-Clause

Copyright (c) Peter Waller and contributors — https://github.com/pwaller/pyfiglet
(BSD-2-Clause; includes bundled FIGlet fonts by various artists, see the
upstream project for full attribution.)

Used optionally for `--figlet` ASCII-art banners.
