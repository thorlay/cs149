#include <algorithm>
#include <cmath>
#include <iostream>
#include <vector>
#include "sine_ispc.h"

int main() {
    constexpr float guard = 12345.0f;
    float max_error = 0.0f;
    for (int n : {0, 1, 3, 4, 5, 7, 8, 9, 19, 32, 33, 1024}) {
        std::vector<float> x(n + 8, 0.0f);
        std::vector<float> a(n + 8, guard), b = a, c = a;
        float expected_sum = 0.0f;
        for (int i = 0; i < n; ++i) {
            x[i] = (i % 17 - 8) * 0.125f;
            expected_sum += x[i];
        }
        ispc::sine_interleaved(n, x.data(), a.data());
        ispc::sine_blocked(n, x.data(), b.data());
        ispc::sine_foreach(n, x.data(), c.data());
        for (int i = 0; i < n; ++i) {
            float expected = std::sin(x[i]);
            for (float value : {a[i], b[i], c[i]}) {
                float error = std::abs(value - expected);
                if (!std::isfinite(value) || error > 1e-6f)
                    return 1;
                max_error = std::max(max_error, error);
            }
        }
        for (int i = n; i < n + 8; ++i)
            if (a[i] != guard || b[i] != guard || c[i] != guard)
                return 2;
        if (ispc::sum_values(n, x.data()) != expected_sum)
            return 3;
    }
    std::cout << "gang_size=" << ispc::gang_size() << '\n'
              << "sizes_checked=12 variants=3 tail_guard=pass reduction=pass\n"
              << "max_sin_error=" << max_error << '\n'
              << "correct=yes\n";
}
