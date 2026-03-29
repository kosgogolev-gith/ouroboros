# Diagnostic logging added to track image pipeline issues

import logging
# ... (existing imports)

# In the build_context method, after initial_model is chosen:
if image_base64:
    logger.info(f"[IMAGE DEBUG] image_base64 present, size={len(image_base64)}, mime={(task.get('image_mime') or 'unknown')}, initial_model={initial_model}")
else:
    logger.info(f"[IMAGE DEBUG] no image_base64 in task, using model {initial_model}")