#include <cstdint>
#include <functional>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

template<class F> void workers(unsigned p,F job) {
    std::vector<std::thread> pool;
    for (unsigned r=1;r<p;++r) pool.emplace_back(job,r);
    job(0);
    for (auto& t:pool) t.join();
}
template<class T,class Op>
std::vector<T> exclusive_scan(const std::vector<T>& input,unsigned p,T identity,Op op) {
    if (p<1 || p>64) throw std::invalid_argument("workers must be 1..64");
    std::size_t n=input.size();
    std::vector<T> out(n),totals(p,identity),bases(p,identity);
    workers(p,[&](unsigned r) {
        std::size_t lo=r*n/p,hi=(r+1)*n/p;
        T acc=identity;
        for (auto i=lo;i<hi;++i) { out[i]=acc;acc=op(acc,input[i]); }
        totals[r]=acc;
    }); // join publishes every local prefix and total
    T acc=identity;
    for (unsigned r=0;r<p;++r) { bases[r]=acc;acc=op(acc,totals[r]); }
    workers(p,[&](unsigned r) {
        for (std::size_t i=r*n/p;i<(r+1)*n/p;++i)
            out[i]=op(bases[r],out[i]); // left base, then local prefix
    });
    return out;
}
template<class T> void verify(const std::vector<T>& x,unsigned p,T identity) {
    auto got=exclusive_scan(x,p,identity,std::plus<T>{});
    T acc=identity;
    for (std::size_t i=0;i<x.size();++i) {
        if (got[i]!=acc) throw std::runtime_error("prefix/order mismatch");
        acc=acc+x[i];
    }
}
int main() {
    try {
        int cases=0;
        for (int n : {0,1,2,3,5,7,8,31,32,33,127,257})
            for (unsigned p : {1,2,3,4,8}) {
                std::vector<std::int64_t> x(n);
                std::vector<std::string> words(n);
                for (int i=0;i<n;++i) {
                    x[i]=i%13-6;
                    words[i]=std::string(1,static_cast<char>('a'+i%4));
                }
                verify(x,p,std::int64_t{0});++cases;
                verify(words,p,std::string{});++cases;
            }
        std::mt19937 rng(149);
        for (int test=0;test<100;++test) {
            std::vector<std::int64_t> x(rng()%513);
            for (auto& v:x) v=static_cast<int>(rng()%19)-9;
            verify(x,1+rng()%8,std::int64_t{0});++cases;
        }
        bool rejected=false;
        try { exclusive_scan(std::vector<int>{1},0,0,std::plus<int>{}); }
        catch (const std::invalid_argument&) { rejected=true; }
        if (!rejected) throw std::runtime_error("invalid worker count accepted");
        auto demo=exclusive_scan(std::vector<int>{2,1,3,4},3,0,std::plus<int>{});
        std::cout<<"exclusive:";
        for (auto v:demo) std::cout<<' '<<v;
        std::cout<<"\ncases="<<cases
                 <<" integer_and_string=pass empty_partitions=pass invalid_workers=pass correct=yes\n";
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
