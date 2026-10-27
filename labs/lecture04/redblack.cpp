#include <algorithm>
#include <cmath>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <numeric>
#include <stdexcept>
#include <thread>
#include <vector>

class Barrier {
    std::mutex mutex;
    std::condition_variable changed;
    const unsigned expected;
    unsigned arrived = 0;
    unsigned generation = 0;
public:
    explicit Barrier(unsigned count) : expected(count) {}
    void wait() {
        std::unique_lock<std::mutex> lock(mutex);
        unsigned my_generation = generation;
        if (++arrived == expected) {
            arrived = 0;
            ++generation;
            changed.notify_all();
        } else {
            changed.wait(lock, [&] { return generation != my_generation; });
        }
    }
};

struct Grid {
    int n, stride;
    std::vector<double> data;
    explicit Grid(int size) : n(size), stride(size+2), data(stride*stride, 0.0) {
        for (int j=0; j<stride; ++j) at(0,j)=1.0;
    }
    double& at(int i,int j) { return data[i*stride+j]; }
    double at(int i,int j) const { return data[i*stride+j]; }
};

// Update only one color and one worker's row interval [lo,hi).
double update(Grid& a, int color, int lo, int hi) {
    double diff=0.0;
    for (int i=lo; i<hi; ++i)
        for (int j=1; j<=a.n; ++j)
            if ((i+j)%2==color) {
                double old=a.at(i,j);
                double next=.2*(old+a.at(i-1,j)+a.at(i+1,j)
                                   +a.at(i,j-1)+a.at(i,j+1));
                a.at(i,j)=next;
                diff+=std::abs(next-old);
            }
    return diff;
}

int serial(Grid& a, int limit, double tolerance) {
    for (int step=1; step<=limit; ++step) {
        double diff=update(a,0,1,a.n+1);
        diff+=update(a,1,1,a.n+1);
        if (diff/(a.n*a.n)<tolerance) return step;
    }
    return limit;
}

int parallel(Grid& a, unsigned workers, int limit, double tolerance) {
    Barrier barrier(workers);
    std::vector<double> partial(workers,0.0);
    bool done=false;
    int completed=0;
    auto worker=[&](unsigned p) {
        int lo=1+p*a.n/workers, hi=1+(p+1)*a.n/workers;
        for (int step=1; step<=limit; ++step) {
            double local=update(a,0,lo,hi);
            barrier.wait(); // B1: every red value is ready for black readers
            local+=update(a,1,lo,hi);
            partial[p]=local;
            barrier.wait(); // B2: black grid and all partials are ready
            if (p==0) {
                double diff=std::accumulate(partial.begin(),partial.end(),0.0);
                completed=step;
                done=diff/(a.n*a.n)<tolerance || step==limit;
            }
            barrier.wait(); // B3: publish the single writer's stop decision
            if (done) break;
        }
    };
    std::vector<std::thread> threads;
    for (unsigned p=1; p<workers; ++p) threads.emplace_back(worker,p);
    worker(0);
    for (auto& t:threads) t.join();
    return completed;
}

double residual(const Grid& a) {
    double result=0;
    for (int i=1;i<=a.n;++i)
        for (int j=1;j<=a.n;++j)
            result=std::max(result,std::abs(4*a.at(i,j)-a.at(i-1,j)
                 -a.at(i+1,j)-a.at(i,j-1)-a.at(i,j+1)));
    return result;
}

void compare(const Grid& a,const Grid& b,double tolerance) {
    for (std::size_t i=0;i<a.data.size();++i)
        if (!std::isfinite(b.data[i]) || std::abs(a.data[i]-b.data[i])>tolerance)
            throw std::runtime_error("Grid mismatch");
    Grid boundary(a.n);
    for (int i=0;i<a.stride;++i)
        for (int j=0;j<a.stride;++j) {
            if (i==0 || j==0 || i==a.n+1 || j==a.n+1)
                if (b.at(i,j)!=boundary.at(i,j))
                    throw std::runtime_error("Boundary changed");
            if (b.at(i,j)<0 || b.at(i,j)>1)
                throw std::runtime_error("Out of expected range");
        }
}

int main() {
    try {
        int cases=0;
        double worst_residual=0;
        for (int n:{1,2,3,5,8})
            for (unsigned p:{1,2,4,8}) {
                for (int steps:{1,2,7,31}) {
                    Grid reference(n), candidate(n);
                    serial(reference,steps,0);
                    int completed=parallel(candidate,p,steps,0);
                    if (completed!=steps) throw std::runtime_error("Lost phase");
                    compare(reference,candidate,1e-12);
                    ++cases;
                }
                Grid reference(n),candidate(n);
                serial(reference,5000,1e-9);
                int steps=parallel(candidate,p,5000,1e-9);
                compare(reference,candidate,1e-8);
                double r=residual(candidate);
                if (steps==5000 || r>1e-7)
                    throw std::runtime_error("Did not converge");
                worst_residual=std::max(worst_residual,r);
                ++cases;
            }
        std::cout<<"cases="<<cases
                 <<" fixed_sweeps=pass convergence=pass boundaries=pass\n"
                 <<"worst_residual="<<worst_residual<<"\ncorrect=yes\n";
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n';
        return 1;
    }
}
