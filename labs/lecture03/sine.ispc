static inline float approximate_sin(float x) {
    float term = x;
    float total = x;
    for (uniform int k = 1; k <= 8; ++k) {
        term *= -x * x / ((2.0f*k) * (2.0f*k+1.0f));
        total += term;
    }
    return total;
}

export uniform int gang_size() {
    return programCount;
}

export void sine_interleaved(uniform int n,
                             uniform float x[], uniform float y[]) {
    for (uniform int base = 0; base < n; base += programCount) {
        int i = base + programIndex;
        if (i < n)
            y[i] = approximate_sin(x[i]);
    }
}

export void sine_blocked(uniform int n,
                         uniform float x[], uniform float y[]) {
    int begin = (programIndex * n) / programCount;
    int end = ((programIndex + 1) * n) / programCount;
    for (int i = begin; i < end; ++i)
        y[i] = approximate_sin(x[i]);
}

export void sine_foreach(uniform int n,
                         uniform float x[], uniform float y[]) {
    foreach (i = 0 ... n)
        y[i] = approximate_sin(x[i]);
}

export uniform float sum_values(uniform int n, uniform float x[]) {
    float partial = 0.0f;
    foreach (i = 0 ... n)
        partial += x[i];
    return reduce_add(partial);
}
