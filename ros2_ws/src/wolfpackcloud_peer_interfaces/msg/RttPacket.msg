# Echoed ping: correlation_id and stamp_sent are preserved across the peer bounce.
# is_reply=true means bounce from peer; stale replies must not be re-echoed.
builtin_interfaces/Time stamp_sent
uint64 correlation_id
int32 counter_value
bool is_reply
