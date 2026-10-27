#include <cuda_runtime.h>
#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <utility>

void check(cudaError_t e) {
    if (e != cudaSuccess) throw std::runtime_error(cudaGetErrorString(e));
}
template<class T> struct DeviceBuffer {
    T* p = nullptr;
    explicit DeviceBuffer(std::size_t n) {
        check(cudaMalloc(reinterpret_cast<void**>(&p),n*sizeof(T)));
    }
    ~DeviceBuffer() { if (p) cudaFree(p); }
    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;
};
__global__ void avg_direct(const float* x,float* y,int n) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if (i<n) {
        float left=i>0?x[i-1]:0.0f;
        float right=i+1<n?x[i+1]:0.0f;
        y[i]=(left+x[i]+right)/3.0f;
    }
}
__global__ void avg_tiled(const float* x,float* y,int n) {
    extern __shared__ float tile[];
    int t=threadIdx.x, width=blockDim.x, base=blockIdx.x*width;
    for (int q=t;q<width+2;q+=width) {
        int g=base+q-1;
        tile[q]=(g>=0 && g<n)?x[g]:0.0f;
    }
    __syncthreads(); // Every thread participates, including tail threads.
    int i=base+t;
    if (i<n) y[i]=(tile[t]+tile[t+1]+tile[t+2])/3.0f;
}
__global__ void matrix_add(const float* a,const float* b,float* c,int nx,int ny) {
    int x=blockIdx.x*blockDim.x+threadIdx.x;
    int y=blockIdx.y*blockDim.y+threadIdx.y;
    if (x<nx && y<ny) {
        int i=y*nx+x;
        c[i]=a[i]+b[i];
    }
}
__global__ void histogram(const int* x,int* bins,int n) {
    int tid=blockIdx.x*blockDim.x+threadIdx.x;
    int step=blockDim.x*gridDim.x;
    for (int i=tid;i<n;i+=step) atomicAdd(&bins[x[i]],1);
}
void compare(const std::vector<float>& got,const std::vector<float>& want) {
    if (got.size()!=want.size()) throw std::runtime_error("size mismatch");
    for (std::size_t i=0;i<got.size();++i)
        if (!std::isfinite(got[i]) || std::abs(got[i]-want[i])>1e-6f)
            throw std::runtime_error("output/tail mismatch");
}
void avg_case(int n,int threads) {
    if (n==0) return; // No zero-sized grid launch.
    std::vector<float> x(n),want(n+8,-999.0f),got(n+8),init(n+8,-999.0f);
    for (int i=0;i<n;++i) x[i]=(i%17-8)*0.25f;
    for (int i=0;i<n;++i) {
        float left=i>0?x[i-1]:0.0f, right=i+1<n?x[i+1]:0.0f;
        want[i]=(left+x[i]+right)/3.0f;
    }
    DeviceBuffer<float> dx(n),dy(n+8);
    check(cudaMemcpy(dx.p,x.data(),n*sizeof(float),cudaMemcpyHostToDevice));
    int blocks=(n+threads-1)/threads;
    for (int mode=0;mode<2;++mode) {
        check(cudaMemcpy(dy.p,init.data(),init.size()*sizeof(float),cudaMemcpyHostToDevice));
        if (mode==0) avg_direct<<<blocks,threads>>>(dx.p,dy.p,n);
        else avg_tiled<<<blocks,threads,(threads+2)*sizeof(float)>>>(dx.p,dy.p,n);
        check(cudaGetLastError());
        check(cudaDeviceSynchronize());
        check(cudaMemcpy(got.data(),dy.p,got.size()*sizeof(float),cudaMemcpyDeviceToHost));
        compare(got,want);
    }
}
void matrix_case(int nx,int ny,int bx,int by) {
    int n=nx*ny;
    if (n==0) return;
    std::vector<float> a(n),b(n),want(n+8,-999.0f),got(n+8),init(n+8,-999.0f);
    for (int i=0;i<n;++i) { a[i]=(i%17-8)*0.25f;b[i]=0.5f;want[i]=a[i]+b[i]; }
    DeviceBuffer<float> da(n),db(n),dc(n+8);
    check(cudaMemcpy(da.p,a.data(),n*sizeof(float),cudaMemcpyHostToDevice));
    check(cudaMemcpy(db.p,b.data(),n*sizeof(float),cudaMemcpyHostToDevice));
    check(cudaMemcpy(dc.p,init.data(),init.size()*sizeof(float),cudaMemcpyHostToDevice));
    dim3 block(bx,by),grid((nx+bx-1)/bx,(ny+by-1)/by);
    matrix_add<<<grid,block>>>(da.p,db.p,dc.p,nx,ny);
    check(cudaGetLastError()); check(cudaDeviceSynchronize());
    check(cudaMemcpy(got.data(),dc.p,got.size()*sizeof(float),cudaMemcpyDeviceToHost));
    compare(got,want);
}
void histogram_case(int n) {
    if (n==0) return;
    std::vector<int> x(n),want(10,0),got(10);
    for (int i=0;i<n;++i) { x[i]=i%10;++want[x[i]]; }
    DeviceBuffer<int> dx(n),bins(10);
    check(cudaMemcpy(dx.p,x.data(),n*sizeof(int),cudaMemcpyHostToDevice));
    check(cudaMemset(bins.p,0,10*sizeof(int)));
    histogram<<<2,128>>>(dx.p,bins.p,n);
    check(cudaGetLastError());check(cudaDeviceSynchronize());
    check(cudaMemcpy(got.data(),bins.p,10*sizeof(int),cudaMemcpyDeviceToHost));
    if (got!=want) throw std::runtime_error("histogram mismatch");
}
int main() {
    try {
        int devices=0;check(cudaGetDeviceCount(&devices));
        if (devices==0) throw std::runtime_error("A CUDA-capable NVIDIA GPU is required");
        check(cudaSetDevice(0));cudaDeviceProp prop{};check(cudaGetDeviceProperties(&prop,0));
        if (prop.maxThreadsPerBlock<256) throw std::runtime_error("Tests require 256 threads/block");
        int avg_cases=0,matrix_cases=0,histogram_cases=0;
        for (int n : {0,1,2,3,5,31,32,33,127,128,129,257}) {
            for (int t : {1,2,7,32,64,128,256}) { avg_case(n,t);++avg_cases; }
            histogram_case(n);++histogram_cases;
        }
        for (auto shape : {std::pair<int,int>{0,0},{1,1},{11,5},{12,6},{17,9},{31,33}})
            for (auto block : {std::pair<int,int>{4,3},{8,4},{16,16}}) {
                matrix_case(shape.first,shape.second,block.first,block.second);++matrix_cases;
            }
        std::cout<<"avg_cases="<<avg_cases<<" matrix_cases="<<matrix_cases
                 <<" histogram_cases="<<histogram_cases<<" tail=pass correct=yes\n";
    } catch (const std::exception& e) {
        std::cerr<<e.what()<<'\n';return 1;
    }
}
