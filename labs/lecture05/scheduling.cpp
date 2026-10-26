#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using Clock = std::chrono::steady_clock;
struct Stats {
    std::uint64_t iterations = 0;
    std::size_t tasks = 0, claims = 0;
    double task_ms = 0;
};

enum class Policy { block, cyclic, dynamic };

std::uint64_t payload(std::size_t i, unsigned rounds) {
    std::uint64_t value = i + 1;
    for (unsigned k = 0; k < rounds; ++k) {
        value ^= value >> 13;
        value *= UINT64_C(0x9e3779b97f4a7c15);
        value += k;
    }
    return value;
}

void run(std::size_t n, unsigned workers, std::size_t chunk,
         Policy policy, bool verify_only) {
    std::vector<unsigned> rounds(n, 4000);
    for (std::size_t i = 0; i < n/4; ++i) rounds[i] = 120000;
    std::vector<std::uint64_t> reference(n), result(n);
    for (std::size_t i = 0; i < n; ++i)
        reference[i] = payload(i, rounds[i]);
    std::vector<std::atomic<unsigned>> visits(n);
    for (auto& item : visits) item.store(0);
    std::vector<Stats> stats(workers);
    std::atomic<std::size_t> next{0};
    auto started = Clock::now();
    auto work = [&](unsigned p) {
        auto execute = [&](std::size_t i) {
            auto begin = Clock::now();
            result[i] = payload(i, rounds[i]);
            stats[p].task_ms += std::chrono::duration<double, std::milli>(
                Clock::now()-begin).count();
            stats[p].iterations += rounds[i];
            ++stats[p].tasks;
            if (verify_only) visits[i].fetch_add(1, std::memory_order_relaxed);
        };
        if (policy == Policy::block) {
            for (std::size_t i = p*n/workers; i < (p+1)*n/workers; ++i)
                execute(i);
        } else if (policy == Policy::cyclic) {
            for (std::size_t i = p; i < n; i += workers) execute(i);
        } else {
            for (;;) {
                auto begin = next.fetch_add(chunk, std::memory_order_relaxed);
                ++stats[p].claims;
                if (begin >= n) break;
                auto end = std::min(begin+chunk, n);
                for (auto i = begin; i < end; ++i) execute(i);
            }
        }
    };
    std::vector<std::thread> pool;
    for (unsigned p = 1; p < workers; ++p) pool.emplace_back(work, p);
    work(0);
    for (auto& thread : pool) thread.join();
    double elapsed = std::chrono::duration<double, std::milli>(
        Clock::now()-started).count();
    if (result != reference) throw std::runtime_error("Wrong output");
    std::size_t tasks = 0, claims = 0;
    for (auto& item : stats) { tasks += item.tasks; claims += item.claims; }
    if (tasks != n) throw std::runtime_error("Wrong task count");
    if (verify_only) {
        for (auto& item : visits)
            if (item.load() != 1) throw std::runtime_error("Repeated/missing task");
    }
    if (policy == Policy::dynamic && claims != (n+chunk-1)/chunk+workers)
        throw std::runtime_error("Wrong claim count");
    if (!verify_only) {
        const char* label = policy == Policy::block ? "block" :
                            policy == Policy::cyclic ? "cyclic" : "dynamic";
        std::cout << label << " chunk=" << chunk << " wall_ms=" << elapsed
                  << " claims=" << claims << " correct=yes\n";
        for (unsigned p = 0; p < workers; ++p)
            std::cout << "  worker=" << p << " tasks=" << stats[p].tasks
                      << " iterations=" << stats[p].iterations
                      << " task_ms=" << stats[p].task_ms << '\n';
    }
}

int main(int argc, char** argv) {
    try {
        std::cout << std::fixed << std::setprecision(3);
        if (argc > 1 && std::string(argv[1]) == "--check") {
            for (std::size_t n : {0, 1, 3, 19, 128, 257})
                for (unsigned p : {1, 2, 4}) {
                    run(n, p, 1, Policy::block, true);
                    run(n, p, 1, Policy::cyclic, true);
                    for (std::size_t chunk : {1, 4, 16, 64})
                        run(n, p, chunk, Policy::dynamic, true);
                }
            std::cout << "cases=108 exact_once=pass outputs=pass all_checks=pass\n";
        } else {
            unsigned p = argc > 1 ? std::stoul(argv[1]) : 4;
            if (p < 1 || p > 64) throw std::runtime_error("workers must be 1..64");
            run(128, p, 1, Policy::block, false);
            run(128, p, 1, Policy::cyclic, false);
            for (std::size_t chunk : {1, 4, 16, 64})
                run(128, p, chunk, Policy::dynamic, false);
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
