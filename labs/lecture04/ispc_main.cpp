#include <cmath>
#include <iostream>
#include <vector>
#include "basics_ispc.h"

int main() {
    for (int n:{0,1,3,4,5,8,9,19,32}) {
        std::vector<float> x(n+8,0), y(2*n+8,12345.0f);
        float total=0;
        for (int i=0;i<n;++i) {
            x[i]=(i-9)*.25f;
            total+=x[i];
        }
        ispc::absolute_repeat(n,x.data(),y.data());
        for (int i=0;i<n;++i)
            if (y[2*i]!=std::abs(x[i]) || y[2*i+1]!=std::abs(x[i])) return 1;
        for (int i=2*n;i<2*n+8;++i)
            if (y[i]!=12345.0f) return 2;
        if (ispc::lesson_sum(n,x.data())!=total) return 3;
    }
    std::cout<<"gang_size="<<ispc::lesson_gang_size()
             <<" sizes_checked=9 absolute_repeat=pass reduction=pass tail=pass\n";
}
