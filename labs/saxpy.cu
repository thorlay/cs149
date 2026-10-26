// Original educational CUDA SAXPY example for cs149 notes.
// Build: nvcc -O3 -std=c++17 saxpy.cu -o saxpy
#include <cuda_runtime.h>

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

#define CUDA_CHECK(expr) do {                                      \
    cudaError_t err = (expr);                                      \
    if (err != cudaSuccess) {                                      \
        std::fprintf(stderr, "CUDA error at %s:%d: %s\\n",       \
                     __FILE__, __LINE__, cudaGetErrorString(err));\
        std::exit(EXIT_FAILURE);                                   \
    }                                                              \
} while (0)

__global__ void saxpy_kernel(int n, float a, const float* x, float* y) {
    for (int i = blockIdx.x * blockDim.x + threadIdx.x;
         i < n; i += gridDim.x * blockDim.x) {
        y[i] = a * x[i] + y[i];
    }
}

int main(int argc, char** argv) {
    const int n = argc > 1 ? std::atoi(argv[1]) : (1 << 20);
    const int threads = argc > 2 ? std::atoi(argv[2]) : 256;
    if (n <= 0 || threads <= 0 || threads > 1024) {
        std::fprintf(stderr, "usage: %s [positive-N] [threads 1..1024]\\n", argv[0]);
        return EXIT_FAILURE;
    }

    const size_t bytes = static_cast<size_t>(n) * sizeof(float);
    const float a = 2.0f;
    std::vector<float> x(n, 1.5f), y(n, 2.0f);
    float *dx = nullptr, *dy = nullptr;
    CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&dx), bytes));
    CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&dy), bytes));

    const int blocks = (n + threads - 1) / threads < 4096
        ? (n + threads - 1) / threads : 4096;

    CUDA_CHECK(cudaFree(nullptr)); // Ensures runtime initialization where supported.

    auto total_start = std::chrono::steady_clock::now();
    CUDA_CHECK(cudaMemcpy(dx, x.data(), bytes, cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(dy, y.data(), bytes, cudaMemcpyHostToDevice));

    cudaEvent_t start, stop;
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    CUDA_CHECK(cudaEventRecord(start));
    saxpy_kernel<<<blocks, threads>>>(n, a, dx, dy);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));

    float kernel_ms = 0.0f;
    CUDA_CHECK(cudaEventElapsedTime(&kernel_ms, start, stop));
    CUDA_CHECK(cudaMemcpy(y.data(), dy, bytes, cudaMemcpyDeviceToHost));
    auto total_stop = std::chrono::steady_clock::now();

    bool ok = true;
    for (float v : y) {
        if (std::fabs(v - 5.0f) > 1e-5f) { ok = false; break; }
    }

    const double total_ms =
        std::chrono::duration<double, std::milli>(total_stop - total_start).count();
    const double effective_gbs =
        kernel_ms > 0 ? (12.0 * n) / (static_cast<double>(kernel_ms) * 1e6) : 0.0;

    std::printf("N=%d threads=%d blocks=%d correct=%s\\n",
                n, threads, blocks, ok ? "yes" : "NO");
    std::printf("kernel-only: %.3f ms\\n", kernel_ms);
    std::printf("H2D+kernel+D2H: %.3f ms\\n", total_ms);
    std::printf("estimated kernel bandwidth: %.2f GB/s\\n", effective_gbs);

    CUDA_CHECK(cudaEventDestroy(start));
    CUDA_CHECK(cudaEventDestroy(stop));
    CUDA_CHECK(cudaFree(dx));
    CUDA_CHECK(cudaFree(dy));
    return ok ? EXIT_SUCCESS : EXIT_FAILURE;
}
