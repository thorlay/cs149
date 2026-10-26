#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <thread>
#include <vector>

double approx_sin(double x, int terms) {
    double term = x;
    double sum = x;
    for (int k = 1; k <= terms; ++k) {
        term *= -x * x / ((2.0 * k) * (2.0 * k + 1.0));
        sum += term;
    }
    return sum;
}

void serial(const std::vector<double>& x,
            std::vector<double>& y, int terms) {
    for (std::size_t i = 0; i < x.size(); ++i)
        y[i] = approx_sin(x[i], terms);
}

void parallel(const std::vector<double>& x,
              std::vector<double>& y,
              int terms, unsigned workers) {
    workers = std::max(1U, workers);
    std::size_t chunk = (x.size() + workers - 1) / workers;

    auto work = [&](unsigned w) {
        std::size_t begin = w * chunk;
        std::size_t end = std::min(begin + chunk, x.size());
        for (std::size_t i = begin; i < end; ++i)
            y[i] = approx_sin(x[i], terms);
    };

    std::vector<std::thread> threads;
    for (unsigned w = 1; w < workers; ++w)
        threads.emplace_back(work, w);
    work(0);
    for (auto& t : threads) t.join();
}

int main(int argc, char** argv) {
    unsigned workers = argc > 1
        ? static_cast<unsigned>(std::stoul(argv[1])) : 4U;
    constexpr std::size_t n = 1 << 19;
    constexpr int terms = 8;
    std::vector<double> x(n), baseline(n), result(n);

    for (std::size_t i = 0; i < n; ++i)
        x[i] = 2.0 * static_cast<double>(i % 1024) / 1023.0 - 1.0;

    auto start = std::chrono::steady_clock::now();
    serial(x, baseline, terms);
    auto split = std::chrono::steady_clock::now();
    parallel(x, result, terms, workers);
    auto end = std::chrono::steady_clock::now();

    double max_diff = 0.0, max_math_error = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        max_diff = std::max(
            max_diff, std::abs(baseline[i] - result[i]));
        max_math_error = std::max(
            max_math_error, std::abs(result[i] - std::sin(x[i])));
    }

    double ts = std::chrono::duration<double, std::milli>(
        split - start).count();
    double tp = std::chrono::duration<double, std::milli>(
        end - split).count();

    std::cout << std::fixed << std::setprecision(3)
              << "workers=" << workers
              << " serial_ms=" << ts
              << " parallel_ms=" << tp
              << " speedup=" << (ts / tp) << "x\n"
              << "max_diff=" << max_diff
              << " max_sin_error=" << max_math_error << "\n";

    bool ok = max_diff < 1e-12 && max_math_error < 1e-12;
    std::cout << "correct=" << (ok ? "yes" : "NO") << "\n";
    return ok ? 0 : 1;
}
