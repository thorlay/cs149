#include <cmath>
#include <iostream>
#include <vector>
#if defined(__AVX2__)
#include <immintrin.h>
#endif

void multiply(const float* a, const float* b, float* out, int n) {
    int i = 0;
#if defined(__AVX2__)
    for (; i + 7 < n; i += 8) {
        __m256 va = _mm256_loadu_ps(a + i);
        __m256 vb = _mm256_loadu_ps(b + i);
        __m256 vc = _mm256_mul_ps(va, vb);
        _mm256_storeu_ps(out + i, vc);
    }
#endif
    for (; i < n; ++i)
        out[i] = a[i] * b[i];
}

int main() {
    constexpr int n = 19;
    std::vector<float> a(n), b(n), out(n);
    for (int i = 0; i < n; ++i) {
        a[i] = static_cast<float>(i + 1);
        b[i] = 2.0f;
    }
    multiply(a.data(), b.data(), out.data(), n);
    for (int i = 0; i < n; ++i) {
        if (std::fabs(out[i] - 2.0f * (i + 1)) > 1e-5f)
            return 1;
    }
    std::cout << "correct=yes n=19 vector_lane_width="
#if defined(__AVX2__)
              << 8
#else
              << 1
#endif
              << "\n";
}
