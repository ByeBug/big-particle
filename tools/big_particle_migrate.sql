-- 将 core_algo_record 表中的数据迁移到 algo_big_particle_detail 表中
INSERT INTO algo_big_particle_detail (stream_id, stream_name, size, record_id, detected_at, created_at)
SELECT stream_id, stream_name, max_size, id, detected_at, created_at
FROM core_algo_record
WHERE algo_name = 'big_particle';
