# sink_pblock.xdc: the constraint the scripted agent session writes into design.xdc (demo_managed_session.py): the sink is held in a pblock beside
# the locked block, never over it (the block's keep-out region is SLICE_X26Y70:SLICE_X37Y91). Used as the extra constraints of one placement arm.
create_pblock pb_sink
resize_pblock pb_sink -add SLICE_X38Y72:SLICE_X45Y90
add_cells_to_pblock pb_sink [get_cells u_sink]
