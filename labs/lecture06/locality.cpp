#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
using Vec = std::vector<float>;
using Clock = std::chrono::steady_clock;

void separate(const Vec& a, const Vec& b, const Vec& c, const Vec& d,
              Vec& t1, Vec& t2, Vec& out) {
    for (std::size_t i=0; i<a.size(); ++i) t1[i]=a[i]+b[i];
    for (std::size_t i=0; i<a.size(); ++i) t2[i]=t1[i]*c[i];
    for (std::size_t i=0; i<a.size(); ++i) out[i]=d[i]+t2[i];
}
void fused(const Vec& a, const Vec& b, const Vec& c, const Vec& d, Vec& out) {
    for (std::size_t i=0; i<a.size(); ++i) out[i]=d[i]+(a[i]+b[i])*c[i];
}
void inputs(Vec& a, Vec& b, Vec& c, Vec& d) {
    for (std::size_t i=0; i<a.size(); ++i) {
        a[i]=static_cast<int>(i%17)-8;
        b[i]=0.25f*static_cast<int>(i%7);
        c[i]=0.5f; d[i]=1.0f;
    }
}
struct Grid {
    int n, stride;
    Vec x;
    explicit Grid(int size):n(size),stride(size+2),x(stride*stride,0) {
        std::fill(x.begin(),x.begin()+stride,1);
    }
    float& at(int i,int j) { return x[i*stride+j]; }
    float at(int i,int j) const { return x[i*stride+j]; }
};
void reference_step(const Grid& in, Grid& out) {
    for (int i=1; i<=in.n; ++i)
        for (int j=1; j<=in.n; ++j)
            out.at(i,j)=0.2f*(in.at(i,j)+in.at(i-1,j)+in.at(i+1,j)
                                  +in.at(i,j-1)+in.at(i,j+1));
}
void stencil(const Grid& in, Grid& out, int tile) {
    for (int ii=1; ii<=in.n; ii+=tile)
        for (int jj=1; jj<=in.n; jj+=tile)
            for (int i=ii; i<std::min(ii+tile,in.n+1); ++i)
                for (int j=jj; j<std::min(jj+tile,in.n+1); ++j)
                    out.at(i,j)=0.2f*(in.at(i,j)+in.at(i-1,j)+in.at(i+1,j)
                                          +in.at(i,j-1)+in.at(i,j+1));
}
void check() {
    int fusion_cases=0, stencil_cases=0;
    for (int n : {0,1,2,3,7,16,31,33,257}) {
        Vec a(n),b(n),c(n),d(n),t1(n),t2(n),x(n),y(n);
        inputs(a,b,c,d);
        separate(a,b,c,d,t1,t2,x); fused(a,b,c,d,y);
        if (x!=y) throw std::runtime_error("fusion mismatch");
        for (int i=0; i<n; ++i) {
            double expected=double(d[i])+(double(a[i])+b[i])*c[i];
            if (x[i]!=expected) throw std::runtime_error("reference mismatch");
        }
        ++fusion_cases;
    }
    for (int n : {1,2,3,7,16,31})
        for (int tile : {1,2,3,8,64})
            for (int steps : {1,2,7}) {
                Grid a(n),b(n),x(n),y(n);
                for (int s=0; s<steps; ++s) {
                    reference_step(a,b); stencil(x,y,tile);
                    std::swap(a.x,b.x); std::swap(x.x,y.x);
                    if (a.x!=x.x) throw std::runtime_error("stencil mismatch");
                }
                for (int i=0; i<n+2; ++i)
                    for (int j=0; j<n+2; ++j) {
                        float v=x.at(i,j);
                        if (!std::isfinite(v)||v<0||v>1)
                            throw std::runtime_error("invalid grid value");
                        if ((i==0 && v!=1) || (i==n+1 && v!=0) ||
                            (i>0 && (j==0||j==n+1) && v!=0))
                            throw std::runtime_error("boundary changed");
                    }
                ++stencil_cases;
            }
    std::cout<<"fusion_cases="<<fusion_cases<<" stencil_cases="<<stencil_cases
             <<" boundaries=pass correct=yes\n";
}
double checksum(const Vec& x) {
    double sum=0;
    for (float v:x) sum+=v;
    return sum;
}
void bench(std::size_t n) {
    Vec a(n),b(n),c(n),d(n),t1(n),t2(n),x(n),y(n);
    inputs(a,b,c,d);
    separate(a,b,c,d,t1,t2,x); fused(a,b,c,d,y);
    if (x!=y) throw std::runtime_error("warmup mismatch");
    std::vector<double> times[2];
    double observed=0;
    for (int rep=0; rep<7; ++rep)
        for (int order=0; order<2; ++order) {
            int mode=(rep+order)%2;
            auto start=Clock::now();
            if (mode==0) separate(a,b,c,d,t1,t2,x);
            else fused(a,b,c,d,y);
            double seconds=std::chrono::duration<double>(Clock::now()-start).count();
            times[mode].push_back(seconds);
            // Observe every timed output outside the timed region.
            observed+=checksum(mode==0 ? x : y);
            if (x!=y) throw std::runtime_error("timed output mismatch");
        }
    std::cout<<std::fixed<<std::setprecision(3);
    for (int mode=0; mode<2; ++mode) {
        std::sort(times[mode].begin(),times[mode].end());
        double t=times[mode][3];
        std::cout<<(mode==0?"separate":"fused")<<" n="<<n
                 <<" median_ms="<<t*1000
                 <<" logical_GB_per_s="<<(mode==0?36.0:20.0)*n/t/1e9<<'\n';
    }
    std::cout<<"observed_checksum="<<observed<<" correct=yes\n";
}
int main(int argc,char** argv) {
    try {
        check();
        if (argc>1) {
            if (std::string(argv[1])!="--bench" || argc>3)
                throw std::runtime_error("usage: locality [--bench [elements]]");
            auto n=argc==3?std::stoull(argv[2]):4194304ULL;
            if (n<1 || n>16777216) throw std::runtime_error("elements must be 1..16777216");
            bench(n);
        }
    } catch (const std::exception& e) {
        std::cerr<<e.what()<<'\n'; return 1;
    }
}
