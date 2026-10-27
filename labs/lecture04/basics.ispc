export uniform int lesson_gang_size() {
    return programCount;
}

export void absolute_repeat(uniform int n,
                            uniform float x[], uniform float y[]) {
    foreach (i = 0 ... n) {
        float v = abs(x[i]);
        y[2*i] = v;
        y[2*i+1] = v;
    }
}

export uniform float lesson_sum(uniform int n, uniform float x[]) {
    float partial = 0.0f;
    foreach (i = 0 ... n)
        partial += x[i];
    return reduce_add(partial);
}
