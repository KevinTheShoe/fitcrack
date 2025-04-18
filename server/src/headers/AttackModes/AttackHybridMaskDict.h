/**
 * @file AttackCombinator.h
 * @brief Header file for creation of Combinator Attack
 * Note, that Hybrid attacks {hashcat -a 6 and 7} are
 * converted to this attack for distribution needs
 *
 * @authors Lukas Zobal (zobal.lukas(at)gmail.com)
 * @date 12. 12. 2018
 * @license MIT, see LICENSE
 */

#ifndef WORKGENERATOR_ATTACKHYBRID_MASKDICT_H_
#define WORKGENERATOR_ATTACKHYBRID_MASKDICT_H_

#include <AttackMode.h>


class CAttackHybridMaskDict : public AttackMode {
public:
	/**
	 * @brief Constructor for Combinator Attack
	 * @param job [in] Instance of CJob which is parent of this attack instance
	 * @param host [in] Instance of CHost which this attack belongs to
	 * @param seconds [in] Number of seconds this instance of attack should take
	 */
	CAttackHybridMaskDict(PtrJob job, PtrHost &host, uint64_t seconds, CSqlLoader *sqlLoader);

	/**
	 * @brief Default destructor
	 */
	~CAttackHybridMaskDict() override = default;

	/**
	 * @brief Creates BOINC workunit, adds entry to fc_workunit
	 * @return True if a workunit was planned, False otherwise
	 */
	bool makeWorkunit() override ;

	virtual bool requiresDicts() const override {return true;}
	virtual bool requiresMasks() const override {return true;}

private:
	/**
	 * @brief Function to generate new CWorkunit for certain host for given time
	 * @return True if workunit was generated successfully, False otherwise
	 */
	bool generateWorkunit() override ;
};

#endif //WORKGENERATOR_ATTACKHYBRID_MASKDICT_H_
