#include "app_entry.h"
#include "log-mel_spectogram.h"
#include "console.h"

void app_main(void)
{
	console_init();
	mel_filterbank_init();
}
