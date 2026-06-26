# Auto-generated from src/neuralspotx/constants.py BOARDS
# by scripts/gen_board_table.py — DO NOT EDIT.
#
# Defines: nsx_board_is_registered(board_name out_var)
#   Sets <out_var> in the parent scope to TRUE when the board name
#   matches a registered packaged board, else FALSE.
#   Board matching is case-insensitive.

set(_NSX_REGISTERED_BOARDS_LOWER
    "apollo2_evb"
    "apollo3_evb"
    "apollo3_evb_cygnus"
    "apollo3p_evb"
    "apollo3p_evb_cygnus"
    "apollo4l_evb"
    "apollo4l_blue_evb"
    "apollo4p_evb"
    "apollo4p_blue_kbr_evb"
    "apollo4p_blue_kxr_evb"
    "apollo5b_evb"
    "apollo510_evb"
    "apollo510b_evb"
    "apollo330mp_evb"
    "apollo510dl_evb"
)

function(nsx_board_is_registered board_name out_var)
    string(TOLOWER "${board_name}" _board_lc)
    if(_board_lc IN_LIST _NSX_REGISTERED_BOARDS_LOWER)
        set(${out_var} TRUE PARENT_SCOPE)
    else()
        set(${out_var} FALSE PARENT_SCOPE)
    endif()
endfunction()
