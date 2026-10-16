# infra/

Hạ tầng chạy hệ thống, tách khỏi code ứng dụng:

- `postgres/init.sql` — bật extension `vector`, `unaccent` (spec 01 FR-05).
- `docker/mentormind.Dockerfile` — image môi trường chạy ứng dụng (architecture §6).
- `docker/docker-compose.*.yml` — **override** của `docker-compose.yml`, mỗi file một đặc thù máy.

`docker-compose.yml` (stack đầy đủ, chạy được trên máy thường) nằm ở gốc repo để `make up` /
`docker compose` dùng trực tiếp. Override chỉ vá đúng phần khác biệt của một loại máy:

| Override | Dùng khi | Vá gì |
|---|---|---|
| `docker/docker-compose.rocm.yml` | GPU **AMD** (MI250 = 1 GCD) | build `Dockerfile.rocm`, bỏ `deploy.devices` kiểu nvidia, gắn `/dev/kfd` + `/dev/dri` |
| `docker/docker-compose.cdi.yml` | Host cấp GPU NVIDIA qua **CDI**, không có nvidia runtime | đổi `deploy.resources` → `devices: nvidia.com/gpu=<N>` |
| `docker/docker-compose.devbox.yml` | Docker **rootless** mà mạng bridge không ra được internet | mọi service dùng `network_mode: host`, gọi nhau qua `127.0.0.1` |

Ba trục này độc lập nhau (vendor GPU / cách cấp GPU / mạng) nên là ba file rời; máy nào cần hai
trục thì xếp chồng hai file. `Makefile` gói sẵn các tổ hợp hay dùng:

```bash
make up                  # máy thường (NVIDIA runtime, mạng bridge)
make up PLATFORM=rocm    # máy AMD
make up PLATFORM=devbox  # máy rootless: cdi + devbox
```
